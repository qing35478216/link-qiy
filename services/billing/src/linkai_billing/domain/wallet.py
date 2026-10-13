"""积分钱包领域模型。

不变量（构造即校验，资金域零容错）：
- balance 为**整数积分**，禁止浮点（类型即约束）；
- balance 恒 >= 0——扣减绝不为负（事务层条件 UPDATE 兜底，领域层前置校验）；
- tenant_id 非空（铁律 6：没有租户的余额无法归属，属于计费事故）。

钱包是"余额视图"，**所有**余额变动必须伴随 LedgerEntry（流水）——
钱包自身不提供直接改余额的公开写方法，写路径只有 services 层经
WalletLedger.apply()（事务内 INSERT 流水 + 条件 UPDATE 余额）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkai_billing.domain.errors import InsufficientCredits
from linkai_billing.domain.ids import date_key, utcnow
from linkai_billing.domain.pricing import DEFAULT_LOW_BALANCE_THRESHOLD


@dataclass
class CreditWallet:
    """租户积分钱包（tenant_id 主键，一行一租户）。"""

    tenant_id: str
    balance: int = 0
    plan: str = "basic"  # 四档版本只读副本（platform 为事实源，经内部端点同步）
    reminder_threshold: int = DEFAULT_LOW_BALANCE_THRESHOLD
    # 最近一次"余额不足提醒"发送日期（UTC YYYY-MM-DD）——提醒幂等，每日最多一次
    low_balance_notified_on: str | None = None
    created_at: object = field(default_factory=utcnow)
    updated_at: object = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("CreditWallet.tenant_id 不能为空（铁律 6 多租户）")
        if not isinstance(self.balance, int) or isinstance(self.balance, bool):
            raise TypeError("balance 必须为整数积分（禁浮点）")
        if self.balance < 0:
            raise ValueError(f"balance 不能为负: {self.balance}")
        if self.reminder_threshold < 0:
            raise ValueError("reminder_threshold 不能为负")

    def can_afford(self, credits: int) -> bool:
        return credits <= self.balance

    def assert_affordable(self, credits: int) -> None:
        """余额前置校验（事务层仍有条件 UPDATE 兜底，双保险）。"""
        if credits > self.balance:
            raise InsufficientCredits(
                f"积分余额不足：需要 {credits}，当前 {self.balance}（请充值后重试）"
            )

    def is_low_balance(self) -> bool:
        """是否低于提醒阈值（0 元余额也视为低——需提醒充值）。"""
        return self.balance < self.reminder_threshold

    def should_remind_today(self, *, today: str | None = None) -> bool:
        """今日是否应发余额提醒（低余额 且 今日未发过——每日一次，防骚扰）。"""
        if not self.is_low_balance():
            return False
        return self.low_balance_notified_on != (today or date_key(utcnow()))
