"""Quota 路由（契约 console-api.yaml Quota 段：版本徽标 + 配额面板）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from linkai_platform.api.deps import AppContext, get_context, get_principal
from linkai_platform.api.schemas import QuotaSummaryResponse, QuotaUsageResponse
from linkai_platform.domain.auth import Principal

router = APIRouter(tags=["Quota"])


@router.get("/quota/summary", response_model=QuotaSummaryResponse)
async def get_quota_summary(
    principal: Principal = Depends(get_principal), ctx: AppContext = Depends(get_context)
) -> QuotaSummaryResponse:
    summary = ctx.quota_service.get_summary(
        tenant_id=principal.tenant_id, user_id=principal.user_id
    )
    return QuotaSummaryResponse(
        plan=summary.plan,
        planBadge=summary.planBadge,
        walletBalance=summary.walletBalance,
        upgradeUrl=summary.upgradeUrl,
        usage=QuotaUsageResponse(
            messagesUsed=summary.usage.messagesUsed if summary.usage else 0,
            messagesLimit=summary.usage.messagesLimit if summary.usage else 0,
            tokensUsed=summary.usage.tokensUsed if summary.usage else 0,
            tokensLimit=summary.usage.tokensLimit if summary.usage else 0,
        ),
    )
