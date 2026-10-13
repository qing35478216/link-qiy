"""订单应用层单测：下单幂等 / 回调验签 + 重放 + 幂等入账 / 关单。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from linkai_billing.domain.errors import OrderNotFound, OrderStateError, PaymentVerifyError
from linkai_billing.domain.ids import utcnow
from linkai_billing.domain.ledger import (
    LedgerEntry,
    LedgerEntryKind,
    LedgerSource,
)
from linkai_billing.domain.orders import OrderStatus
from linkai_billing.domain.ports import Clock
from linkai_billing.infra.order_repo import SqlAlchemyOrderRepository
from linkai_billing.infra.payment_mock import MockPaymentProvider
from linkai_billing.infra.wallet_repo import SqlAlchemyLedgerQuery, SqlAlchemyWalletLedger
from linkai_billing.services.metering_service import MeteringService
from linkai_billing.services.order_service import OrderService
from tests.conftest import make_event

SECRET = "test-payment-secret-0123456789"


class FakeClock:
    def __init__(self) -> None:
        self._now = utcnow()

    def now(self) -> datetime:
        return self._now

    def advance(self, *, minutes: int) -> None:
        self._now = self._now + timedelta(minutes=minutes)


def _service(session: object, clock: Clock | None = None) -> OrderService:
    return OrderService(
        orders=SqlAlchemyOrderRepository(session),  # type: ignore[arg-type]
        ledger=SqlAlchemyWalletLedger(session),  # type: ignore[arg-type]
        payment=MockPaymentProvider(secret=SECRET),
        clock=clock,
    )


def test_create_order_uses_package_prices_not_client_input(file_session_factory: object) -> None:
    """下单金额以套餐定价为权威（客户端无法指定金额——防篡改）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        view, created = service.create_order(
            tenant_id="t-1", package_code="tier_10k", request_id="req-1"
        )
        session.commit()
    assert created
    assert view.credits == 10_000
    assert view.amount_fen == 1_900
    assert view.status == "pending"


def test_create_order_idempotent_by_request_id(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        first, created1 = service.create_order(
            tenant_id="t-1", package_code="tier_10k", request_id="req-1"
        )
        second, created2 = service.create_order(
            tenant_id="t-1", package_code="tier_10k", request_id="req-1"
        )
        session.commit()
    assert created1 and not created2
    assert first.order_no == second.order_no  # 同一订单，不重复建单


def test_invalid_package_rejected(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    from linkai_billing.domain.errors import InvalidPackage

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        with pytest.raises(InvalidPackage):
            service.create_order(tenant_id="t-1", package_code="tier_free", request_id="req-x")
        session.rollback()


def test_mock_pay_credits_wallet_once(file_session_factory: object) -> None:
    """Mock 支付全流程：下单 → 支付 → 积分到账（一次）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        view, _ = service.create_order(tenant_id="t-1", package_code="tier_1k", request_id="req-1")
        result = service.pay_order(tenant_id="t-1", order_no=view.order_no)
        session.commit()
    assert result.credited
    assert result.credits == 1_000
    assert result.balance_after == 1_000

    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get("t-1")
        order = SqlAlchemyOrderRepository(session).get("t-1", view.order_no)
        session.commit()
    assert wallet is not None and wallet.balance == 1_000
    assert order is not None and order.status is OrderStatus.PAID
    assert order.provider_trade_no is not None


def test_double_pay_rejected(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        view, _ = service.create_order(tenant_id="t-1", package_code="tier_1k", request_id="req-1")
        service.pay_order(tenant_id="t-1", order_no=view.order_no)
        session.commit()
    with factory() as session:
        service = _service(session)
        with pytest.raises(OrderStateError):
            service.pay_order(tenant_id="t-1", order_no=view.order_no)
        session.rollback()


def test_callback_replay_does_not_double_credit(file_session_factory: object) -> None:
    """★幂等★ 同一订单重复回调只入账一次（工单：订单号重复回调只入账一次）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    payment = MockPaymentProvider(secret=SECRET)

    with factory() as session:
        service = _service(session)
        view, _ = service.create_order(tenant_id="t-1", package_code="tier_10k", request_id="req-1")
        session.commit()

    # 用真实订单号构造渠道回调（模拟渠道异步通知）
    callback = payment.build_callback(
        order_no=view.order_no,
        amount_fen=1_900,
        callback_id="cb-1",
        trade_no="trade-1",
    )

    with factory() as session:
        service = _service(session)
        first = service.handle_callback(callback)
        session.commit()
    assert first.credited

    with factory() as session:
        service = _service(session)
        second = service.handle_callback(callback)  # 重放同一回调
        session.commit()
    assert not second.credited  # 幂等命中，未二次入账

    with factory() as session:
        wallet = SqlAlchemyWalletLedger(session).get("t-1")
        session.commit()
    assert wallet is not None and wallet.balance == 10_000  # 只加了一次


def test_callback_tampered_amount_ignored(file_session_factory: object) -> None:
    """回调金额被篡改：验签失败 → PaymentVerifyError（安全事件）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    payment = MockPaymentProvider(secret=SECRET)
    callback = payment.build_callback(
        order_no="RO-TAMPER", amount_fen=100, callback_id="cb-1", trade_no="trade-1"
    )
    callback["payload"]["amountFen"] = "1"  # 篡改金额（签名对不上）
    with factory() as session:
        service = _service(session)
        with pytest.raises(PaymentVerifyError):
            service.handle_callback(callback)
        session.rollback()


def test_callback_replay_window_enforced(file_session_factory: object) -> None:
    """回调时间戳超窗（>300s）→ 拒绝（重放防护）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    payment = MockPaymentProvider(secret=SECRET)
    stale = payment.build_callback(
        order_no="RO-STALE",
        amount_fen=1_900,
        callback_id="cb-1",
        trade_no="trade-1",
        now=datetime.now(UTC).timestamp() - 600,
    )
    with factory() as session:
        service = _service(session)
        with pytest.raises(PaymentVerifyError, match="重放窗口"):
            service.handle_callback(stale)
        session.rollback()


def test_callback_unknown_order_rejected(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    payment = MockPaymentProvider(secret=SECRET)
    callback = payment.build_callback(
        order_no="RO-GHOST", amount_fen=1_900, callback_id="cb-1", trade_no="trade-1"
    )
    with factory() as session:
        service = _service(session)
        with pytest.raises(OrderNotFound):
            service.handle_callback(callback)
        session.rollback()


def test_close_expired_pending_orders(file_session_factory: object) -> None:
    """超时未付订单关单（30 分钟口径）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    clock = FakeClock()
    with factory() as session:
        service = _service(session, clock=clock)
        view, _ = service.create_order(tenant_id="t-1", package_code="tier_1k", request_id="req-1")
        session.commit()

    clock.advance(minutes=31)
    with factory() as session:
        service = _service(session, clock=clock)
        closed = service.close_expired()
        session.commit()
    assert closed == [view.order_no]

    with factory() as session:
        order = SqlAlchemyOrderRepository(session).get("t-1", view.order_no)
        session.commit()
    assert order is not None and order.status is OrderStatus.CLOSED

    # 已关订单不可支付
    with factory() as session:
        service = _service(session, clock=clock)
        with pytest.raises(OrderStateError):
            service.pay_order(tenant_id="t-1", order_no=view.order_no)
        session.rollback()


def test_order_not_found_for_other_tenant(file_session_factory: object) -> None:
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        service = _service(session)
        view, _ = service.create_order(tenant_id="t-1", package_code="tier_1k", request_id="req-1")
        session.commit()
    with factory() as session:
        service = _service(session)
        with pytest.raises(OrderNotFound):
            service.get_order(tenant_id="t-other", order_no=view.order_no)
        session.rollback()


def test_ledger_usage_totals_exclude_failed(file_session_factory: object) -> None:
    """用量聚合只计 applied 且非 failed（配额面板口径）。"""
    from sqlalchemy.orm import sessionmaker

    factory: sessionmaker = file_session_factory  # type: ignore[assignment]
    with factory() as session:
        ledger = SqlAlchemyWalletLedger(session)
        ledger.apply(
            LedgerEntry(
                entry_id="le_seed",
                tenant_id="t-1",
                request_id="recharge:seed",
                kind=LedgerEntryKind.RECHARGE,
                source=LedgerSource.ORDER,
                delta=10_000,
                credits_charged=10_000,
            )
        )
        session.commit()
    with factory() as session:
        service = MeteringService(ledger=SqlAlchemyWalletLedger(session))
        service.process(make_event(event_id="evt-ok", credits=100))
        service.process(make_event(event_id="evt-fail", credits=0, outcome="failed"))
        session.commit()
    with factory() as session:
        messages, tokens = SqlAlchemyLedgerQuery(session).usage_totals("t-1")
        session.commit()
    assert messages == 1  # failed 不计入消息数
    assert tokens == 200
