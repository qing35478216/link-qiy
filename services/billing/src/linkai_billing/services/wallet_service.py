"""钱包应用层：余额查询 / 签到（幂等）/ 余额提醒。

签到幂等双保险：
1. 快路径：先查 (tenant_id, date) 签到记录；
2. 硬保证：仓储 record() 内部唯一约束命中返回 False（并发签到先到先得）。

同日重复签到**只加一次**（工单验收③；DB 唯一约束 + 领域双查）。
本层零框架 import（sqlalchemy 只在 infra）。
"""

from __future__ import annotations

from dataclasses import dataclass

from linkai_billing.domain.ids import date_key, utcnow
from linkai_billing.domain.ledger import LedgerApplyResult
from linkai_billing.domain.ports import CheckInRepository, WalletLedger, WalletRepository
from linkai_billing.domain.pricing import CHECKIN_REWARD_CREDITS
from linkai_billing.services.metering_service import build_checkin_entry


@dataclass(frozen=True)
class WalletView:
    """钱包读模型（API 序列化用）。"""

    tenant_id: str
    balance: int
    plan: str
    reminder_threshold: int
    low_balance: bool
    should_remind: bool


@dataclass(frozen=True)
class CheckInResult:
    """签到结果。already=True 表示当日已签到（幂等命中，未重复加分）。"""

    tenant_id: str
    date: str
    credits_granted: int
    already: bool
    balance_after: int


class WalletService:
    def __init__(
        self,
        *,
        wallets: WalletRepository,
        ledger: WalletLedger,
        checkins: CheckInRepository,
    ) -> None:
        self._wallets = wallets
        self._ledger = ledger
        self._checkins = checkins

    def get_wallet(self, tenant_id: str) -> WalletView:
        """查钱包（不存在返回零值视图——不自动开户，查询无副作用）。"""
        wallet = self._wallets.get(tenant_id)
        if wallet is None:
            return WalletView(
                tenant_id=tenant_id,
                balance=0,
                plan="basic",
                reminder_threshold=0,
                low_balance=True,
                should_remind=False,
            )
        return WalletView(
            tenant_id=wallet.tenant_id,
            balance=wallet.balance,
            plan=wallet.plan,
            reminder_threshold=wallet.reminder_threshold,
            low_balance=wallet.is_low_balance(),
            should_remind=wallet.should_remind_today(),
        )

    def check_in(self, tenant_id: str, *, today: str | None = None) -> CheckInResult:
        """每日签到（幂等：同日重复只加一次；UTC 日期口径）。"""
        date = today or date_key(utcnow())
        wallet = self._wallets.ensure(tenant_id)
        balance_before = wallet.balance

        if self._checkins.has_checked_in(tenant_id, date):
            return CheckInResult(
                tenant_id=tenant_id,
                date=date,
                credits_granted=0,
                already=True,
                balance_after=balance_before,
            )

        if not self._checkins.record(tenant_id, date, CHECKIN_REWARD_CREDITS):
            # 并发签到：唯一约束命中 → 当日已签到（幂等）
            return CheckInResult(
                tenant_id=tenant_id,
                date=date,
                credits_granted=0,
                already=True,
                balance_after=balance_before,
            )

        entry = build_checkin_entry(
            tenant_id=tenant_id, date=date, reward=CHECKIN_REWARD_CREDITS
        )
        applied = self._ledger.apply(entry)
        if applied.result is LedgerApplyResult.DUPLICATE:
            # 防御（正常不可达：签到行先落）：已入账过，按幂等处理
            return CheckInResult(
                tenant_id=tenant_id,
                date=date,
                credits_granted=0,
                already=True,
                balance_after=balance_before,
            )

        wallet_after = self._wallets.get(tenant_id)
        return CheckInResult(
            tenant_id=tenant_id,
            date=date,
            credits_granted=CHECKIN_REWARD_CREDITS,
            already=False,
            balance_after=(
                wallet_after.balance
                if wallet_after is not None
                else (applied.balance_after or balance_before + CHECKIN_REWARD_CREDITS)
            ),
        )

    def mark_reminded(self, tenant_id: str, *, today: str | None = None) -> None:
        """记录"今日已提醒"（提醒发送成功后调用；每日最多一次）。"""
        date = today or date_key(utcnow())
        wallet = self._wallets.ensure(tenant_id)
        wallet.low_balance_notified_on = date
        self._wallets.save(wallet)

    def set_reminder_threshold(self, tenant_id: str, threshold: int) -> WalletView:
        """设置余额提醒阈值（整数积分）。"""
        if threshold < 0:
            raise ValueError("提醒阈值不能为负")
        wallet = self._wallets.ensure(tenant_id)
        wallet.reminder_threshold = threshold
        self._wallets.save(wallet)
        return self.get_wallet(tenant_id)

    def set_plan(self, tenant_id: str, plan: str) -> WalletView:
        """同步版本（platform 事件同步入口；内部 API 调用，铁律 6 校验租户）。"""
        from linkai_billing.domain.quota import Plan, tier_of

        tier_of(plan)  # 非法版本名在此抛错
        wallet = self._wallets.ensure(tenant_id)
        wallet.plan = str(Plan(plan))
        self._wallets.save(wallet)
        return self.get_wallet(tenant_id)
