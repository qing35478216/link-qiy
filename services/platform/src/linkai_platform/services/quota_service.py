"""配额面板编排（应用层）：GET /quota/summary。

Phase 0：plan/planBadge 来自账户域；walletBalance 与 usage 为占位（0），
计费域（T-007）落地后由计量事件聚合替换。
"""

from __future__ import annotations

from linkai_platform.domain import quota as quota_domain
from linkai_platform.domain.quota import QuotaSummary, QuotaUsage
from linkai_platform.domain.repositories import UserRepository
from linkai_platform.domain.users import UserNotFound


class QuotaService:
    def __init__(self, *, users: UserRepository) -> None:
        self._users = users

    def get_summary(self, *, tenant_id: str, user_id: str) -> QuotaSummary:
        user = self._users.get(tenant_id, user_id)
        if user is None:
            raise UserNotFound("用户不存在或不属于当前租户")
        return QuotaSummary(
            plan=user.plan.value,
            planBadge=quota_domain.plan_badge(user.plan),
            walletBalance=0,  # TODO(T-007): billing 积分余额对接
            upgradeUrl=quota_domain.UPGRADE_URL,
            usage=QuotaUsage(),  # TODO(T-007): 计量事件聚合（消息数/token 数）
        )
