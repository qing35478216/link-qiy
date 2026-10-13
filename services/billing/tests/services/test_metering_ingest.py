"""计量 ingest/drain 单测（Stream 端口双实现：内存 + fakeredis 真 Redis 语义）。"""

from __future__ import annotations

import pytest

from linkai_billing.domain.ledger import LedgerApplyResult
from linkai_billing.domain.metering import MeteringEventIn, MeteringOutcome
from linkai_billing.infra.wallet_repo import SqlAlchemyWalletLedger
from linkai_billing.services.metering_service import (
    MeteringIngestService,
    MeteringService,
)
from tests.conftest import make_event


def _seed(session: object, *, credits: int = 10_000) -> None:
    from linkai_billing.domain.ids import utcnow
    from linkai_billing.domain.ledger import (
        LedgerEntry,
        LedgerEntryKind,
        LedgerSource,
    )

    ledger = SqlAlchemyWalletLedger(session)  # type: ignore[arg-type]
    ledger.apply(
        LedgerEntry(
            entry_id="le_seed",
            tenant_id="t-1",
            request_id="recharge:seed",
            kind=LedgerEntryKind.RECHARGE,
            source=LedgerSource.ORDER,
            delta=credits,
            credits_charged=credits,
            occurred_at=utcnow(),
        )
    )


def test_ingest_applies_and_acks(file_session_factory: object, stream: object) -> None:
    """入流 → drain → 扣减 → ACK；余额精确。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        _seed(session)
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        ingest = MeteringIngestService(
            stream=stream, processor=service.process  # type: ignore[arg-type]
        )
        outcome = ingest.ingest(make_event(event_id="evt-1", credits=100))
        session.commit()
    assert outcome.result is LedgerApplyResult.APPLIED
    assert outcome.balance_after == 9_900
    assert stream.pending_ids() == []  # 已 ACK

    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get("t-1")
        session.commit()
    assert wallet is not None and wallet.balance == 9_900


def test_reingest_same_event_is_duplicate(file_session_factory: object, stream: object) -> None:
    """同一事件二次投递（重投模拟）：流水有两条、DB 只扣一次。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        _seed(session)
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        ingest = MeteringIngestService(
            stream=stream, processor=service.process  # type: ignore[arg-type]
        )
        first = ingest.ingest(make_event(event_id="evt-dup", credits=100))
        second = ingest.ingest(make_event(event_id="evt-dup", credits=100))
        session.commit()
    assert first.result is LedgerApplyResult.APPLIED
    assert second.result is LedgerApplyResult.DUPLICATE

    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get("t-1")
        session.commit()
    assert wallet is not None and wallet.balance == 9_900


def test_drain_retries_unacked_entries(file_session_factory: object, stream: object) -> None:
    """未 ACK 条目下次 drain 重投（至少一次）；处理后不再重投。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        _seed(session)
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        ingest = MeteringIngestService(
            stream=stream, processor=service.process  # type: ignore[arg-type]
        )
        ingest.append(make_event(event_id="evt-retry", credits=100))
        session.commit()

    # 模拟"读到没 ACK 就崩"：不调用 drain 的 ack 路径——直接再 drain 也能处理
    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        ingest = MeteringIngestService(
            stream=stream, processor=service.process  # type: ignore[arg-type]
        )
        outcomes = ingest.drain()
        session.commit()
    assert [o.result for o in outcomes] == [LedgerApplyResult.APPLIED]
    assert stream.pending_ids() == []


def test_redis_stream_impl_matches_port_semantics() -> None:
    """Redis 实现（fakeredis）与内存实现同端口同语义：append/read/ack/range。"""
    fakeredis = pytest.importorskip("fakeredis")
    from linkai_billing.infra.redis_stream import RedisMeteringStream

    client = fakeredis.FakeStrictRedis()
    stream = RedisMeteringStream(client, key="billing:metering:events", group="billing")

    payload = {"event_id": "evt-r1", "tenant_id": "t-1", "credits": "100", "outcome": "success"}
    entry_id = stream.append("evt-r1", payload)
    assert entry_id

    entries = stream.read_group(consumer="w-1", count=10)
    assert [e[1]["event_id"] for e in entries] == ["evt-r1"]
    assert stream.pending_ids() == [entries[0][0]]

    stream.ack(entries[0][0])
    assert stream.pending_ids() == []
    assert len(stream.range_all()) == 1
    # ACK 后不再投递
    assert stream.read_group(consumer="w-1", count=10) == []


def test_redis_stream_redelivers_unacked() -> None:
    """fakeredis：未 ACK 条目重投（至少一次语义）。"""
    pytest.importorskip("fakeredis")
    import fakeredis

    from linkai_billing.infra.redis_stream import RedisMeteringStream

    client = fakeredis.FakeStrictRedis()
    stream = RedisMeteringStream(client, key="s2", group="billing")
    stream.append("evt-r2", {"event_id": "evt-r2", "tenant_id": "t-1", "credits": "1"})
    first = stream.read_group(consumer="w-1", count=10)
    assert len(first) == 1
    # 未 ACK → 重投（XAUTOCLAIM min-idle 0）
    again = stream.read_group(consumer="w-1", count=10)
    assert [e[1]["event_id"] for e in again] == ["evt-r2"]
    stream.ack(first[0][0])
    assert stream.read_group(consumer="w-1", count=10) == []


def test_metering_event_in_validation_via_payload() -> None:
    """drain 路径的载荷校验：坏载荷显式抛错（不静默吞计费字段）。"""
    with pytest.raises(ValueError):
        MeteringEventIn.from_payload({"event_id": "e", "credits": 1})  # 缺 tenant_id
    with pytest.raises(ValueError):
        MeteringEventIn.from_payload(
            {"event_id": "e", "tenant_id": "t", "credits": 1, "outcome": "bogus"}
        )


def test_ingest_payload_contains_tenant_and_trace(
    file_session_factory: object, stream: object
) -> None:
    """流水载荷带租户与追踪字段（对账按 tenant:request_id 对齐）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    event = MeteringEventIn(
        event_id="evt-trace",
        tenant_id="t-9",
        credits=10,
        outcome=MeteringOutcome.SUCCESS,
        provider="qwen",
        model_code="qwen-max",
        trace_id="trace-9",
        app_code="app-9",
    )
    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        ingest = MeteringIngestService(
            stream=stream, processor=service.process  # type: ignore[arg-type]
        )
        ingest.append(event)
        session.commit()
    entries = stream.range_all()
    assert entries[0][1]["tenant_id"] == "t-9"
    assert entries[0][1]["trace_id"] == "trace-9"
    assert entries[0][1]["app_code"] == "app-9"
