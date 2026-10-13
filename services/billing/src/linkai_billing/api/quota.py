"""配额路由：GET /quota/summary（契约 Quota 段，真实数据）+ 权益校验。

`/quota/summary` 与契约 console-api.yaml#/QuotaSummary 对齐——
billing 提供真实 walletBalance/usage（platform 占位 0 的替换源，
经 API 同步，不直连库表；见 quota_service 模块 docstring）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from linkai_billing.api.deps import AppContext, get_context, get_principal
from linkai_billing.api.schemas import (
    QuotaCheckRequest,
    QuotaCheckResponse,
    QuotaSummaryResponse,
    QuotaUsageResponse,
)
from linkai_billing.domain.auth import Principal
from linkai_billing.domain.quota import Dimension, usage_limit_of

router = APIRouter(tags=["Quota"])


@router.get("/quota/summary", response_model=QuotaSummaryResponse)
async def get_quota_summary(
    principal: Principal = Depends(get_principal), ctx: AppContext = Depends(get_context)
) -> QuotaSummaryResponse:
    summary = ctx.quota_service.get_summary(tenant_id=principal.tenant_id)
    return QuotaSummaryResponse(
        plan=summary.plan,
        planBadge=summary.plan_badge,
        walletBalance=summary.wallet_balance,
        upgradeUrl=summary.upgrade_url,
        usage=QuotaUsageResponse(
            messagesUsed=summary.usage.messages_used,
            tokensUsed=summary.usage.tokens_used,
        ),
        monthlyCreditGrant=summary.monthly_credit_grant,
    )


@router.post("/v1/quota/check", response_model=QuotaCheckResponse)
async def check_quota(
    body: QuotaCheckRequest,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> QuotaCheckResponse:
    """权益用量校验（超限抛 QuotaExceeded → 403 + details）。

    通过返回 allowed=true；超限走统一错误响应（403 QUOTA_EXCEEDED），
    details 携带 dimension/limit/used/plan 供控制台渲染升级引导。
    """
    plan = ctx.quota_service.plan_of(principal.tenant_id)
    ctx.quota_service.check_dimension(
        plan=plan, dimension=body.dimension, used=body.used, increment=body.increment
    )
    return QuotaCheckResponse(
        allowed=True,
        plan=plan,
        dimension=body.dimension,
        used=body.used,
        increment=body.increment,
        limit=usage_limit_of(plan, Dimension(body.dimension)),
    )
