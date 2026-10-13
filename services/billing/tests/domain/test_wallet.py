"""钱包领域单测（不变量：整数积分 / 非负 / 提醒策略）。"""

from __future__ import annotations

import pytest

from linkai_billing.domain.wallet import CreditWallet


def test_wallet_rejects_float_balance() -> None:
    with pytest.raises(TypeError):
        CreditWallet(tenant_id="t-1", balance=100.5)  # type: ignore[arg-type]


def test_wallet_rejects_negative_balance() -> None:
    with pytest.raises(ValueError, match="不能为负"):
        CreditWallet(tenant_id="t-1", balance=-1)


def test_wallet_rejects_empty_tenant() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        CreditWallet(tenant_id="")


def test_should_remind_once_per_day() -> None:
    wallet = CreditWallet(tenant_id="t-1", balance=10, reminder_threshold=100)
    assert wallet.is_low_balance()
    assert wallet.should_remind_today(today="2026-10-14")
    wallet.low_balance_notified_on = "2026-10-14"
    assert not wallet.should_remind_today(today="2026-10-14")
    assert wallet.should_remind_today(today="2026-10-15")


def test_no_remind_when_balance_healthy() -> None:
    wallet = CreditWallet(tenant_id="t-1", balance=5_000, reminder_threshold=100)
    assert not wallet.should_remind_today(today="2026-10-14")


def test_assert_affordable_raises_insufficient() -> None:
    from linkai_billing.domain.errors import InsufficientCredits

    wallet = CreditWallet(tenant_id="t-1", balance=50)
    assert wallet.can_afford(50)
    assert not wallet.can_afford(51)
    with pytest.raises(InsufficientCredits) as exc_info:
        wallet.assert_affordable(51)
    assert exc_info.value.http_status == 402
