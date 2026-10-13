"""价格体系（docs/01 第十部分 `/console/price` 实测口径）。

铁律：**金额一律整数**——积分为整数积分，人民币为整数分（fen）。
全程无浮点：套餐定价以"分"字面量定义，杜绝 2.90 这类十进制在二进制
浮点下的表示误差（0.1 式抖动在资金域是事故）。

四档充值套餐（实测）：
    1000 积分 ¥2.90（体验）｜10000 积分 ¥19.00｜100000 积分 ¥170.00｜500000 积分 ¥800.00
每日签到（实测单次）：57 积分。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RechargePackage:
    """充值套餐（不可变值对象）。

    `credits` 到账积分；`amount_fen` 人民币金额（分，整数）；
    `label`/`tag` 为控制台定价页展示字段（tag 如"体验/API 调用最佳"）。
    """

    code: str
    credits: int
    amount_fen: int
    label: str
    tag: str | None = None

    @property
    def amount_yuan_display(self) -> str:
        """展示用金额字符串（分 → 元，两位小数；仅用于渲染，不参与计算）。"""
        return f"{self.amount_fen / 100:.2f}"


#: 四档充值套餐（docs/01 第十部分实测；顺序即定价页展示顺序）
RECHARGE_PACKAGES: tuple[RechargePackage, ...] = (
    RechargePackage(
        code="tier_1k", credits=1_000, amount_fen=290, label="1000 积分", tag="体验"
    ),
    RechargePackage(code="tier_10k", credits=10_000, amount_fen=1_900, label="10000 积分"),
    RechargePackage(
        code="tier_100k",
        credits=100_000,
        amount_fen=17_000,
        label="100000 积分",
        tag="API 调用最佳",
    ),
    RechargePackage(
        code="tier_500k", credits=500_000, amount_fen=80_000, label="500000 积分", tag="企业优选"
    ),
)

_PACKAGES_BY_CODE: dict[str, RechargePackage] = {p.code: p for p in RECHARGE_PACKAGES}


def find_package(code: str) -> RechargePackage:
    """按编码取套餐；不存在抛 InvalidPackage（四档之外一律拒绝）。"""
    from linkai_billing.domain.errors import InvalidPackage

    package = _PACKAGES_BY_CODE.get(code)
    if package is None:
        raise InvalidPackage(f"充值套餐不存在: {code!r}（可用: {sorted(_PACKAGES_BY_CODE)}）")
    return package


#: 每日签到积分（docs/01 第十部分实测单次 57）
CHECKIN_REWARD_CREDITS: int = 57

#: 默认余额提醒阈值（积分）：余额低于该值触发提醒。
#: 实测截图未见明确数值，取 100（约一次 tier_1k 充值的 1/10，仅一次低价调用量级），
#: 租户级可在钱包上覆盖（wallets.reminder_threshold）。
DEFAULT_LOW_BALANCE_THRESHOLD: int = 100

#: 充值订单支付超时（分钟）：超时 pending 订单允许关单
ORDER_PAY_TIMEOUT_MINUTES: int = 30

#: 支付回调重放防护窗口（秒）：回调时间戳超过该窗口视为过期
PAYMENT_CALLBACK_TTL_SECONDS: int = 300
