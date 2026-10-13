"""订单状态机领域单测（金额整数 / 非法流转拒绝）。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from linkai_billing.domain.errors import OrderStateError
from linkai_billing.domain.orders import OrderStatus, RechargeOrder

FROZEN_NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def make_order(**overrides: object) -> RechargeOrder:
    defaults: dict[str, object] = {
        "order_no": "RO20261014120000ABCD1234",
        "tenant_id": "t-1",
        "request_id": "req-1",
        "package_code": "tier_10k",
        "credits": 10_000,
        "amount_fen": 1_900,
    }
    defaults.update(overrides)
    return RechargeOrder(**defaults)  # type: ignore[arg-type]


def test_order_rejects_float_amounts() -> None:
    with pytest.raises(TypeError):
        make_order(amount_fen=19.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        make_order(credits=10000.0)  # type: ignore[arg-type]


def test_order_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        make_order(credits=0)
    with pytest.raises(ValueError):
        make_order(amount_fen=0)


def test_happy_path_pay() -> None:
    order = make_order()
    order.mark_paid(provider_trade_no="trade-1", callback_id="cb-1", now=FROZEN_NOW)
    assert order.status is OrderStatus.PAID
    assert order.provider_trade_no == "trade-1"
    assert order.callback_id == "cb-1"
    assert order.paid_at == FROZEN_NOW


def test_double_pay_rejected() -> None:
    order = make_order()
    order.mark_paid(provider_trade_no="trade-1", callback_id="cb-1", now=FROZEN_NOW)
    with pytest.raises(OrderStateError) as exc_info:
        order.mark_paid(provider_trade_no="trade-2", callback_id="cb-2", now=FROZEN_NOW)
    assert exc_info.value.code == "ORDER_STATE_ERROR"


def test_pay_after_close_rejected() -> None:
    order = make_order()
    order.mark_closed(now=FROZEN_NOW)
    with pytest.raises(OrderStateError):
        order.mark_paid(provider_trade_no="trade-1", callback_id="cb-1", now=FROZEN_NOW)


def test_close_paths() -> None:
    pending = make_order()
    pending.mark_closed(now=FROZEN_NOW)
    assert pending.status is OrderStatus.CLOSED

    paid = make_order()
    paid.mark_paid(provider_trade_no="trade-1", callback_id="cb-1", now=FROZEN_NOW)
    paid.mark_closed(now=FROZEN_NOW)
    assert paid.status is OrderStatus.CLOSED

    closed = make_order()
    closed.mark_closed(now=FROZEN_NOW)
    with pytest.raises(OrderStateError):
        closed.mark_closed(now=FROZEN_NOW)


def test_refund_only_from_paid() -> None:
    paid = make_order()
    paid.mark_paid(provider_trade_no="trade-1", callback_id="cb-1", now=FROZEN_NOW)
    paid.mark_refunded(now=FROZEN_NOW)
    assert paid.status is OrderStatus.REFUNDED

    pending = make_order()
    with pytest.raises(OrderStateError):
        pending.mark_refunded(now=FROZEN_NOW)
