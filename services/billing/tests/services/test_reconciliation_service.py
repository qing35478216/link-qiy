"""对账应用层单测（内存 Stream：一致不告警 / 丢事件告警 / 留痕落库）。"""

from __future__ import annotations

from linkai_billing.domain.ids import utcnow
from linkai_billing.domain.ledger import (
    LedgerEntry,
    LedgerEntryKind,
    LedgerSource,
)
from linkai_billing.infra.recon_run_store import SqlAlchemyReconciliationRunStore
from linkai_billing.infra.wallet_repo import SqlAlchemyLedgerQuery, SqlAlchemyWalletLedger
from linkai_billing.services.metering_service import MeteringService
from linkai_billing.services.reconciliation_service import ReconciliationService
from tests.conftest import make_event


def _seed_and_ingest(
    session: object, stream: object, *, event_ids: list[str], credits: int = 10_000
) -> None:
    from linkai_billing.services.metering_service import MeteringIngestService

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
    service = MeteringService(ledger=ledger)
    ingest = MeteringIngestService(stream=stream, processor=service.process)  # type: ignore[arg-type]
    for event_id in event_ids:
        ingest.ingest(make_event(event_id=event_id, credits=100))


def test_reconciliation_clean_run(file_session_factory: object, stream: object) -> None:
    """流水与 DB 一致：matched 全等、无差异、不告警、留痕落库。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        _seed_and_ingest(session, stream, event_ids=[f"evt-{i}" for i in range(5)])
        service = ReconciliationService(
            stream=stream,  # type: ignore[arg-type]
            ledger=SqlAlchemyLedgerQuery(session),
            run_store=SqlAlchemyReconciliationRunStore(session),
        )
        outcome = service.run()
        session.commit()
    report = outcome.report
    assert report.stream_count == 5
    assert report.db_count == 5
    assert report.matched == 5
    assert report.diff_count == 0
    assert not report.alert
    assert not outcome.frozen_settlement
    assert outcome.run_id is not None


def test_reconciliation_detects_missing_in_db_and_alerts(
    file_session_factory: object, stream: object
) -> None:
    """流水有、DB 无（模拟消费丢失）：差异超阈值 → 告警 + 冻结结算信号。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        _seed_and_ingest(session, stream, event_ids=[f"evt-{i}" for i in range(3)])
        # 模拟"入流了但从未被消费"：直接 XADD 一条不进 DB 的事件
        stream.append(  # type: ignore[attr-defined]
            "evt-lost",
            {
                "event_id": "evt-lost",
                "tenant_id": "t-1",
                "credits": "100",
                "outcome": "success",
                "provider": "openai",
                "model_code": "gpt-4o-mini",
                "prompt_tokens": "0",
                "completion_tokens": "0",
                "total_tokens": "0",
                "latency_ms": "0",
                "attempt": "1",
                "occurred_at": utcnow().isoformat(),
            },
        )
        service = ReconciliationService(
            stream=stream,  # type: ignore[arg-type]
            ledger=SqlAlchemyLedgerQuery(session),
            run_store=SqlAlchemyReconciliationRunStore(session),
        )
        outcome = service.run()
        session.commit()
    report = outcome.report
    assert report.stream_count == 4
    assert report.db_count == 3
    assert "t-1:evt-lost" in report.missing_in_db
    assert report.alert  # 差异率 1/4 = 25% >> 0.01%
    assert outcome.frozen_settlement


def test_reconciliation_run_persisted(file_session_factory: object, stream: object) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from linkai_billing.infra.models import ReconciliationRunModel

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        _seed_and_ingest(session, stream, event_ids=["evt-a", "evt-b"])
        service = ReconciliationService(
            stream=stream,  # type: ignore[arg-type]
            ledger=SqlAlchemyLedgerQuery(session),
            run_store=SqlAlchemyReconciliationRunStore(session),
        )
        outcome = service.run(scope="daily")
        session.commit()
        row = session.execute(select(ReconciliationRunModel)).scalars().one()
    assert row.run_scope == "daily"
    assert row.stream_count == 2
    assert row.matched == 2
    assert row.alert in (False, 0)
    assert outcome.run_id == row.id
