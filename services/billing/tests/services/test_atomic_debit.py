"""**资金核心用例**：原子扣减 + 幂等 + 防负余额（SQLite 文件库真实并发）。

验收对应（工单 T-007）：
- ② 扣减接口幂等：同一 request_id 并发 10 次只生效一次；
- ① 金额一律整数（类型即约束 + 场景覆盖）。

并发方法：10 线程 + Barrier 统一发令（最大化竞争窗口），每线程独立
Session/连接（文件库，真实写竞争）——不是单连接串行假并发。
"""

from __future__ import annotations

from linkai_billing.domain.ids import utcnow
from linkai_billing.domain.ledger import (
    LedgerApplyResult,
    LedgerEntry,
    LedgerEntryKind,
    LedgerEntryStatus,
    LedgerSource,
)
from linkai_billing.domain.ports import WalletLedger
from linkai_billing.infra.wallet_repo import SqlAlchemyWalletLedger
from linkai_billing.services.metering_service import MeteringService
from tests.conftest import make_event, run_in_threads


def _seed(session_factory: object, *, tenant_id: str = "t-1", credits: int = 10_000) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        ledger = SqlAlchemyWalletLedger(session)
        ledger.apply(
            LedgerEntry(
                entry_id="le_seed",
                tenant_id=tenant_id,
                request_id="recharge:seed",
                kind=LedgerEntryKind.RECHARGE,
                source=LedgerSource.ORDER,
                delta=credits,
                status=LedgerEntryStatus.APPLIED,
                credits_charged=credits,
                occurred_at=utcnow(),
            )
        )
        session.commit()


def _balance(session_factory: object, tenant_id: str = "t-1") -> int:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get(tenant_id)
        session.commit()
        assert wallet is not None
        return wallet.balance


def test_concurrent_same_request_id_debits_exactly_once(file_session_factory: object) -> None:
    """★核心★ 同一 request_id 并发 10 次：恰好 1 次生效、9 次幂等命中。"""
    _seed(file_session_factory, credits=10_000)
    event = make_event(event_id="evt-race", credits=100, tenant_id="t-1")

    def worker(_index: int) -> LedgerApplyResult:
        from sqlalchemy.orm import sessionmaker

        factory: sessionmaker = file_session_factory  # type: ignore[assignment]
        with factory() as session:
            service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
            outcome = service.process(event)
            session.commit()
            return outcome.result

    results = run_in_threads(10, worker)
    applied = [r for r in results if r is LedgerApplyResult.APPLIED]
    duplicates = [r for r in results if r is LedgerApplyResult.DUPLICATE]
    assert len(applied) == 1, f"应恰好一次生效: {results}"
    assert len(duplicates) == 9, f"其余应幂等命中: {results}"

    # 余额精确：10000 - 100（一次且仅一次）
    assert _balance(file_session_factory) == 9_900


def test_concurrent_distinct_events_never_negative(file_session_factory: object) -> None:
    """★核心★ 10 个不同事件抢 500 积分（每个 100）：恰好 5 扣成功、
    5 个 blocked 留痕，余额为 0——**绝不为负**（条件 UPDATE 原子性）。"""
    _seed(file_session_factory, credits=500)

    def worker(index: int) -> LedgerApplyResult:
        from sqlalchemy.orm import sessionmaker

        factory: sessionmaker = file_session_factory  # type: ignore[assignment]
        with factory() as session:
            service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
            outcome = service.process(make_event(event_id=f"evt-distinct-{index}", credits=100))
            session.commit()
            return outcome.result

    results = run_in_threads(10, worker)
    applied = [r for r in results if r is LedgerApplyResult.APPLIED]
    blocked = [r for r in results if r is LedgerApplyResult.BLOCKED]
    assert len(applied) == 5, f"应恰好 5 笔扣成: {results}"
    assert len(blocked) == 5, f"应恰好 5 笔 blocked: {results}"
    assert _balance(file_session_factory) == 0


def test_duplicate_request_id_with_different_content_rejected(file_session_factory: object) -> None:
    """幂等键相同但内容不一致 → DuplicateRequestId（防重放篡改）。"""
    from sqlalchemy.orm import sessionmaker

    from linkai_billing.domain.errors import DuplicateRequestId

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=10_000)

    with factory() as session:
        ledger: WalletLedger = SqlAlchemyWalletLedger(session)
        ledger.apply(_debit_entry(request_id="evt-x", credits=100))
        session.commit()

    with factory() as session:
        ledger = SqlAlchemyWalletLedger(session)
        try:
            ledger.apply(_debit_entry(request_id="evt-x", credits=999))  # 同键不同值
            session.commit()
        except DuplicateRequestId as exc:
            session.rollback()
            assert exc.code == "DUPLICATE_REQUEST_ID"
        else:
            raise AssertionError("同键不同内容应被拒绝")
    assert _balance(file_session_factory) == 9_900  # 未被二次扣减


def test_blocked_is_terminal_for_request_id(file_session_factory: object) -> None:
    """余额不足 blocked 后，充值再重试同一 request_id → DUPLICATE
    （事件终态化，防止补充值后被追溯扣旧账）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=50)

    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        outcome = service.process(make_event(event_id="evt-blocked", credits=100))
        session.commit()
    assert outcome.result is LedgerApplyResult.BLOCKED
    assert outcome.balance_after == 50
    assert _balance(file_session_factory) == 50

    # 充值 10000 后重试同一事件——不得补扣
    _seed_extra(file_session_factory, credits=10_000, request_id="recharge:topup")
    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        outcome = service.process(make_event(event_id="evt-blocked", credits=100))
        session.commit()
    assert outcome.result is LedgerApplyResult.DUPLICATE
    assert _balance(file_session_factory) == 10_050


def test_failed_event_records_zero_delta(file_session_factory: object) -> None:
    """FAILED 事件：delta=0 留痕（对账可见失败面），不扣费。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=10_000)

    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        outcome = service.process(
            make_event(
                event_id="evt-failed", credits=0, outcome="failed", error_code="upstream_500"
            )
        )
        session.commit()
    assert outcome.result is LedgerApplyResult.APPLIED
    assert outcome.credits_charged == 0
    assert _balance(file_session_factory) == 10_000


def test_zero_credit_free_model_applied(file_session_factory: object) -> None:
    """免费模型 0 积分：applied 留痕，余额不动。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=10_000)
    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        outcome = service.process(make_event(event_id="evt-free", credits=0))
        session.commit()
    assert outcome.result is LedgerApplyResult.APPLIED
    assert _balance(file_session_factory) == 10_000


def _debit_entry(*, request_id: str, credits: int, tenant_id: str = "t-1") -> LedgerEntry:
    return LedgerEntry(
        entry_id=f"le_{request_id}",
        tenant_id=tenant_id,
        request_id=request_id,
        kind=LedgerEntryKind.DEBIT,
        source=LedgerSource.METERING,
        delta=-credits,
        status=LedgerEntryStatus.APPLIED,
        credits_charged=credits,
        occurred_at=utcnow(),
    )


def _seed_extra(session_factory: object, *, credits: int, request_id: str) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        ledger = SqlAlchemyWalletLedger(session)
        ledger.apply(
            LedgerEntry(
                entry_id=f"le_{request_id}",
                tenant_id="t-1",
                request_id=request_id,
                kind=LedgerEntryKind.RECHARGE,
                source=LedgerSource.ORDER,
                delta=credits,
                status=LedgerEntryStatus.APPLIED,
                credits_charged=credits,
                occurred_at=utcnow(),
            )
        )
        session.commit()
