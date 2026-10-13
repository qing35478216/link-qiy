"""价格体系领域单测（docs/01 第十部分实测口径；金额整数禁浮点）。"""

from __future__ import annotations

import pytest

from linkai_billing.domain.errors import InvalidPackage
from linkai_billing.domain.pricing import (
    CHECKIN_REWARD_CREDITS,
    DEFAULT_LOW_BALANCE_THRESHOLD,
    ORDER_PAY_TIMEOUT_MINUTES,
    PAYMENT_CALLBACK_TTL_SECONDS,
    RECHARGE_PACKAGES,
    find_package,
)


def test_recharge_packages_match_docs_measured_values() -> None:
    """四档套餐与 docs/01 第十部分实测逐档一致（积分 + 整数分）。"""
    assert [(p.code, p.credits, p.amount_fen) for p in RECHARGE_PACKAGES] == [
        ("tier_1k", 1_000, 290),
        ("tier_10k", 10_000, 1_900),
        ("tier_100k", 100_000, 17_000),
        ("tier_500k", 500_000, 80_000),
    ]


def test_packages_are_integers_not_floats() -> None:
    """金额/积分一律 int（布尔也算 int 的特例也排除——类型即约束）。"""
    for package in RECHARGE_PACKAGES:
        assert isinstance(package.credits, int) and not isinstance(package.credits, bool)
        assert isinstance(package.amount_fen, int) and not isinstance(package.amount_fen, bool)


def test_amount_yuan_display_renders_two_decimals() -> None:
    """展示用元字符串两位小数（仅渲染，不参与计算）。"""
    assert RECHARGE_PACKAGES[0].amount_yuan_display == "2.90"
    assert RECHARGE_PACKAGES[3].amount_yuan_display == "800.00"


def test_find_package_hit_and_miss() -> None:
    assert find_package("tier_100k").credits == 100_000
    with pytest.raises(InvalidPackage) as exc_info:
        find_package("tier_free")
    assert exc_info.value.code == "INVALID_PACKAGE"


def test_checkin_reward_is_measured_57() -> None:
    """签到单次 57 积分（docs/01 实测）。"""
    assert CHECKIN_REWARD_CREDITS == 57


def test_operational_constants() -> None:
    assert DEFAULT_LOW_BALANCE_THRESHOLD == 100
    assert ORDER_PAY_TIMEOUT_MINUTES == 30
    assert PAYMENT_CALLBACK_TTL_SECONDS == 300
