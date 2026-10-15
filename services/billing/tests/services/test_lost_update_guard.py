"""丢失更新（lost update）防护回归——严明二审 B1（BLOCKING）+ N2。

B1：wallet save() 整行回写 balance，会把并发扣减抹掉
   （plan 同步读 100 → 计量扣减提交 →90 → plan UPDATE 写回 100）。
   修复：save() 只显式更新 plan / reminder_threshold /
   low_balance_notified_on 三列，balance 只准经 apply() 条件 UPDATE。
N2：order save() 无条件覆盖 status。修复：条件 UPDATE
   （WHERE status IN expect_status）+ rowcount 校验，落败转幂等响应。
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from linkai_billing.domain.ledger import LedgerApplyResult
from linkai_billing.domain.orders import OrderStatus
from linkai_billing.infra.order_repo import SqlAlchemyOrderRepository
from linkai_billing.infra.wallet_repo import SqlAlchemyWalletLedger
from linkai_billing.services.metering_service import MeteringService
from linkai_billing.services.wallet_service import WalletService
from tests.conftest import make_event, run_in_threads

SECRET = "test-payment-secret-0123456789"


def _wallet_service(session: object) -> WalletService:
    from linkai_billing.infra.order_repo import SqlAlchemyCheckInRepository

    ledger = SqlAlchemyWalletLedger(session)  # type: ignore[arg-type]
    return WalletService(
        wallets=ledger,
        ledger=ledger,
        checkins=SqlAlchemyCheckInRepository(session),  # type: ignore[arg-type]
    )


def _seed(session_factory: object, *, tenant_id: str = "t-1", credits: int = 100) -> None:
    from linkai_billing.domain.ids import utcnow
    from linkai_billing.domain.ledger import (
        LedgerEntry,
        LedgerEntryKind,
        LedgerSource,
    )

    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        SqlAlchemyWalletLedger(session).apply(
            LedgerEntry(
                entry_id="le_seed",
                tenant_id=tenant_id,
                request_id="recharge:seed",
                kind=LedgerEntryKind.RECHARGE,
                source=LedgerSource.ORDER,
                delta=credits,
                credits_charged=credits,
                occurred_at=utcnow(),
            )
        )
        session.commit()


def _balance(session_factory: object, tenant_id: str = "t-1") -> int:
    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get(tenant_id)
        session.commit()
        assert wallet is not None
        return wallet.balance


def _plan(session_factory: object, tenant_id: str = "t-1") -> str:
    factory: sessionmaker = session_factory  # type: ignore[assignment]
    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get(tenant_id)
        session.commit()
        assert wallet is not None
        return wallet.plan


# —— B1：wallet save() 绝不回写 balance ——


def test_save_never_writes_back_stale_balance(file_session_factory: object) -> None:
    """确定性复现 B1 时序（双会话，无线程）：

    ① 同步会话读钱包（内存实体 balance=100，读事务即结束）
    ② 计量会话扣减 10 并提交（DB → 90）
    ③ 同步会话凭①的旧实体 save()——只准改 plan，余额必须保持 90
    旧实现此处把 balance 写回 100，扣减被抹掉（资损）。
    """
    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=100)

    with factory() as sync_session:
        ledger = SqlAlchemyWalletLedger(sync_session)
        stale_wallet = ledger.get("t-1")  # ① 读：内存快照 balance=100
        assert stale_wallet is not None and stale_wallet.balance == 100
        sync_session.commit()  # 读事务结束（实体留在内存，快照即"旧值"）

        with factory() as debit_session:  # ② 并发扣减提交
            service = MeteringService(ledger=SqlAlchemyWalletLedger(debit_session))
            outcome = service.process(make_event(event_id="evt-b1", credits=10))
            debit_session.commit()
        assert outcome.result is LedgerApplyResult.APPLIED

        stale_wallet.plan = "pro"  # ③ 凭旧实体写回（只应动 plan 列）
        ledger.save(stale_wallet)
        sync_session.commit()

    assert _balance(file_session_factory) == 90  # 扣减未被抹掉
    assert _plan(file_session_factory) == "pro"  # plan 同步生效


def test_concurrent_debit_and_plan_sync_keeps_balance(file_session_factory: object) -> None:
    """★B1 并发★ 10 线程 Barrier：5 线程扣减（各 10）+ 5 线程 plan 同步。

    断言：最终余额 = 100 - 5×10 = 50（并发扣减一分不丢），plan=pro。
    """
    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=100)

    def worker(index: int) -> str:
        with factory() as session:
            if index < 5:
                service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
                service.process(make_event(event_id=f"evt-race-{index}", credits=10))
            else:
                _wallet_service(session).set_plan("t-1", "pro")
            session.commit()
            return "ok"

    results = run_in_threads(10, worker)
    assert results == ["ok"] * 10
    assert _balance(file_session_factory) == 50  # 扣减未被 plan 同步抹掉
    assert _plan(file_session_factory) == "pro"


def test_mark_reminded_and_threshold_do_not_touch_balance(
    file_session_factory: object,
) -> None:
    """mark_reminded / set_reminder_threshold 同样只动三列（同一修复面）。"""
    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=100)
    with factory() as session:
        service = _wallet_service(session)
        service.set_reminder_threshold("t-1", 500)
        service.mark_reminded("t-1", today="2026-10-14")
        session.commit()
    assert _balance(file_session_factory) == 100
    with factory() as session:
        view = _wallet_service(session).get_wallet("t-1")
        session.commit()
    assert view.reminder_threshold == 500
    assert view.should_remind is False  # 今日已提醒


# —— N2：order save() 条件 UPDATE + 并发回调单次入账 ——


def _order_service(session: object) -> object:
    from linkai_billing.infra.payment_mock import MockPaymentProvider
    from linkai_billing.services.order_service import OrderService

    return OrderService(
        orders=SqlAlchemyOrderRepository(session),  # type: ignore[arg-type]
        ledger=SqlAlchemyWalletLedger(session),  # type: ignore[arg-type]
        payment=MockPaymentProvider(secret=SECRET),
    )


def test_concurrent_duplicate_callback_credits_once(file_session_factory: object) -> None:
    """★N2 并发★ 两路回调同时打到同一 pending 订单（Barrier 发令）。

    断言：恰好一路 credited=true；钱包只入账一次；订单终态 PAID；
    落败方不抛错（转幂等响应 credited=false，渠道重试友好）。
    """
    from linkai_billing.infra.payment_mock import MockPaymentProvider

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=0)
    payment = MockPaymentProvider(secret=SECRET)

    with factory() as session:
        service = _order_service(session)
        view, _ = service.create_order(  # type: ignore[union-attr]
            tenant_id="t-1", package_code="tier_10k", request_id="req-race"
        )
        session.commit()
    order_no = view.order_no

    callback = payment.build_callback(
        order_no=order_no, amount_fen=1_900, callback_id="cb-race", trade_no="trade-race"
    )

    def worker(_index: int) -> tuple[bool, int | None]:
        with factory() as session:
            service = _order_service(session)
            result = service.handle_callback(callback)  # type: ignore[union-attr]
            session.commit()
            return result.credited, result.balance_after

    results = run_in_threads(2, worker)
    credited_flags = [r[0] for r in results]
    assert sorted(credited_flags) == [False, True], f"应恰好一路入账: {results}"

    # 钱包只加一次（10000），订单 PAID
    assert _balance(file_session_factory) == 10_000
    with factory() as session:
        order = SqlAlchemyOrderRepository(session).get_by_order_no_fresh(order_no)
        session.commit()
    assert order is not None
    assert order.status is OrderStatus.PAID
    assert order.callback_id == "cb-race"


def test_save_rejects_when_status_moved(file_session_factory: object) -> None:
    """条件 UPDATE 直接验证：持"过期 pending 实体"保存 → 拒绝（N2）。

    模拟并发读-改-写：第二路拿到订单时还是 pending，等它要写回时
    第一路已把订单推向 paid——DB 层条件不满足，写回必须失败，
    且不覆盖第一路的渠道数据（provider_trade_no/callback_id）。
    """
    from linkai_billing.domain.errors import OrderStateError
    from linkai_billing.domain.orders import RechargeOrder

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    _seed(file_session_factory, credits=0)
    with factory() as session:
        service = _order_service(session)
        view, _ = service.create_order(  # type: ignore[union-attr]
            tenant_id="t-1", package_code="tier_1k", request_id="req-cond"
        )
        session.commit()

    # 第一路：正常支付并提交
    with factory() as session:
        repo = SqlAlchemyOrderRepository(session)
        order = repo.get("t-1", view.order_no)
        assert order is not None
        order.mark_paid(provider_trade_no="t", callback_id="c")
        repo.save(order, expect_status=(OrderStatus.PENDING,))
        session.commit()

    # 第二路：持有过期实体（状态认知= pending，DB 实际= paid）
    with factory() as session:
        repo = SqlAlchemyOrderRepository(session)
        stale = RechargeOrder(
            order_no=view.order_no,
            tenant_id="t-1",
            request_id="req-cond",
            package_code="tier_1k",
            credits=1_000,
            amount_fen=290,
            status=OrderStatus.PENDING,
        )
        stale.mark_paid(provider_trade_no="t2", callback_id="c2")
        try:
            repo.save(stale, expect_status=(OrderStatus.PENDING,))
            session.commit()
        except OrderStateError as exc:
            session.rollback()
            assert exc.code == "ORDER_STATE_ERROR"
        else:
            raise AssertionError("状态已被并发迁移的保存应被拒绝")

    # DB 里的仍是第一次支付的渠道数据（没被第二次覆盖）
    with factory() as session:
        final = SqlAlchemyOrderRepository(session).get_by_order_no_fresh(view.order_no)
        session.commit()
    assert final is not None
    assert final.provider_trade_no == "t"
    assert final.callback_id == "c"
