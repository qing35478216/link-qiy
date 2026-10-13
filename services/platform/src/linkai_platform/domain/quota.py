"""配额域（Phase 0）：四档权益矩阵中与平台侧相关的部分 + 面板数据值对象。

完整配额矩阵见 docs/01 第十部分。计费规则由 billing（T-007）负责；
本模块只提供平台服务端可判定的静态配额（应用数上限）与面板占位数据。
"""

from __future__ import annotations

from dataclasses import dataclass

from linkai_platform.domain.users import Plan

# 应用数上限（docs/01 第十部分四档矩阵；None = 不限）
APP_LIMITS: dict[Plan, int | None] = {
    Plan.BASIC: 3,
    Plan.STANDARD: 10,
    Plan.PRO: 30,
    Plan.ENTERPRISE: None,
}

# 版本徽标文案（/console/price 实测口径）
PLAN_BADGES: dict[Plan, str] = {
    Plan.BASIC: "基础版",
    Plan.STANDARD: "标准版",
    Plan.PRO: "专业版",
    Plan.ENTERPRISE: "企业版",
}

UPGRADE_URL = "/console/price"


@dataclass(frozen=True)
class QuotaUsage:
    messagesUsed: int = 0
    messagesLimit: int = 0
    tokensUsed: int = 0
    tokensLimit: int = 0


@dataclass(frozen=True)
class QuotaSummary:
    """配额面板（契约 QuotaSummary）。walletBalance/usage 为占位，T-007 计费域对接。"""

    plan: str
    planBadge: str
    walletBalance: int = 0
    upgradeUrl: str = UPGRADE_URL
    usage: QuotaUsage | None = None


def assert_app_limit(plan: Plan, current_count: int) -> None:
    """应用数配额校验（创建前调用）。超出抛 AppLimitExceeded。"""
    from linkai_platform.domain.apps import AppLimitExceeded

    limit = APP_LIMITS[plan]
    if limit is not None and current_count >= limit:
        raise AppLimitExceeded(
            f"当前版本最多创建 {limit} 个应用（{PLAN_BADGES[plan]}），请升级后重试"
        )


def plan_badge(plan: Plan) -> str:
    return PLAN_BADGES[plan]
