"""配额应用层：GET /quota/summary 真实数据 + 权益校验（R-01）。

数据来源决策（工单要求"经 API 或事件同步，你定并记录"）：
- **walletBalance/usage：billing 本域事实**（钱包表 + 流水聚合）；
- **plan：platform 事实源的只读副本**（wallets.plan）——经内部端点
  `PUT /internal/v1/tenants/{tenant_id}/plan` 同步（platform 套餐变更
  时调用，Phase 0 无 MQ 时的同步通道；Phase 1 改领域事件）；
- platform 现有 `/quota/summary` 的 walletBalance=0 占位由其调用
  billing `GET /internal/v1/quota/summary` 替换（**不直连 platform 库表**，
  也不直连 billing 库表——跨服务只走 API/事件，docs/03 §3.1）。

usage 口径：本月（UTC）计费消息数 / token 总数；`limit` 缺失 = 不限制
（LinkAI 实测以积分约束用量，消息/Token 无硬上限——控制台 QuotaBadge
  对缺失 limit 优雅降级，不渲染 "/ limit"）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from linkai_billing.domain.ids import month_key, utcnow
from linkai_billing.domain.ports import LedgerQuery, WalletRepository
from linkai_billing.domain.quota import (
    Dimension,
    Feature,
    Plan,
    assert_feature,
    assert_quota,
    tier_of,
)
from linkai_billing.domain.wallet import CreditWallet


@dataclass(frozen=True)
class QuotaUsageView:
    messages_used: int = 0
    tokens_used: int = 0


@dataclass(frozen=True)
class QuotaSummaryView:
    """契约 console-api.yaml#/QuotaSummary（camelCase 由 api 层序列化）。"""

    plan: str
    plan_badge: str
    wallet_balance: int
    upgrade_url: str
    usage: QuotaUsageView
    monthly_credit_grant: int | None = None


@dataclass(frozen=True)
class EntitlementView:
    """权益矩阵全量（定价页/内部查询用）。"""

    plan: str
    badge: str
    limits: dict[str, int | None]
    features: dict[str, bool]


class QuotaService:
    def __init__(self, *, wallets: WalletRepository, ledger: LedgerQuery) -> None:
        self._wallets = wallets
        self._ledger = ledger

    def get_summary(self, *, tenant_id: str, now: datetime | None = None) -> QuotaSummaryView:
        wallet = self._wallets.get(tenant_id)
        balance = wallet.balance if wallet is not None else 0
        plan = wallet.plan if wallet is not None else str(Plan.BASIC)
        tier = tier_of(plan)
        moment = now or utcnow()
        month_start = datetime(
            moment.astimezone(UTC).year, moment.astimezone(UTC).month, 1, tzinfo=UTC
        )
        messages, tokens = self._ledger.usage_totals(tenant_id, since=month_start)
        return QuotaSummaryView(
            plan=str(tier.plan),
            plan_badge=tier.badge,
            wallet_balance=balance,
            upgrade_url="/console/price",
            usage=QuotaUsageView(messages_used=messages, tokens_used=tokens),
            monthly_credit_grant=tier.monthly_credit_grant,
        )

    def get_entitlements(self, *, plan: str) -> EntitlementView:
        tier = tier_of(plan)
        limits: dict[str, int | None] = {}
        features: dict[str, bool] = {}
        for field_name in (
            "app_limit",
            "workflow_limit",
            "plugin_limit",
            "super_assistant_limit",
            "cloud_pc_limit",
            "knowledge_file_limit",
            "knowledge_segment_limit",
            "knowledge_file_bytes_limit",
            "db_row_limit",
            "team_member_limit",
            "import_page_limit",
        ):
            limits[field_name.removesuffix("_limit")] = getattr(tier, field_name)
        for field_name in (
            "custom_model",
            "remote_database",
            "data_dashboard",
            "channel_access",
            "client_management",
            "rate_limit_config",
            "human_transfer",
            "aggregated_chat",
            "team_space",
            "open_api_advanced",
            "cloud_pc",
        ):
            features[field_name] = getattr(tier, field_name)
        return EntitlementView(
            plan=str(tier.plan), badge=tier.badge, limits=limits, features=features
        )

    def check_dimension(
        self, *, plan: str, dimension: str, used: int, increment: int = 1
    ) -> None:
        """用量上限校验（超限抛 QuotaExceeded，api 层映射 403 + details）。"""
        assert_quota(plan, Dimension(dimension), used=used, increment=increment)

    def check_feature(self, *, plan: str, feature: str) -> None:
        """功能开关校验（未开放抛 FeatureNotAvailable）。"""
        assert_feature(plan, Feature(feature))

    def plan_of(self, tenant_id: str) -> str:
        wallet = self._wallets.get(tenant_id)
        return wallet.plan if wallet is not None else str(Plan.BASIC)

    def current_month(self, now: datetime | None = None) -> str:
        return month_key(now or utcnow())

    def wallet_balance(self, tenant_id: str) -> int:
        wallet: CreditWallet | None = self._wallets.get(tenant_id)
        return wallet.balance if wallet is not None else 0
