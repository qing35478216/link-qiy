"""内部面路由（服务间）：计量事件消费 / plan 同步 / 支付回调 / 对账触发。

鉴权：X-Internal-Token 共享密钥（deps.require_internal）。
契约外端点（console-api.yaml 未含内部面；Phase 1 契约化时进
service-api.yaml 或独立 internal-api.yaml——已记入 T-007 交付说明）。
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header

from linkai_billing.api.deps import AppContext, get_context, require_internal
from linkai_billing.api.schemas import (
    MeteringEventPayload,
    MeteringEventResult,
    MeteringIngestResponse,
    PaymentCallbackBody,
    PayOrderResponse,
    PlanSyncRequest,
    ReconciliationResponse,
)
from linkai_billing.domain.errors import InvalidToken
from linkai_billing.domain.metering import MeteringEventIn, MeteringOutcome

recon_logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/internal/v1", tags=["Internal"], dependencies=[Depends(require_internal)]
)


@router.post("/metering/events", response_model=MeteringIngestResponse)
async def ingest_metering_events(
    events: list[MeteringEventPayload],
    ctx: AppContext = Depends(get_context),
) -> MeteringIngestResponse:
    """消费 MeteringEvent（model-proxy → billing；幂等键 = eventId）。

    流程：XADD 入流水 → 同步 drain 处理 → ACK。崩溃时未 ACK 事件重投，
    幂等保证不重复扣减（至少一次 + 幂等 = 恰好一次效果）。
    """
    results: list[MeteringEventResult] = []
    for payload in events:
        event = MeteringEventIn(
            event_id=payload.eventId,
            tenant_id=payload.tenantId,
            credits=payload.credits,
            outcome=MeteringOutcome(payload.outcome),
            provider=payload.provider,
            model_code=payload.modelCode,
            prompt_tokens=payload.promptTokens,
            completion_tokens=payload.completionTokens,
            total_tokens=payload.totalTokens,
            latency_ms=payload.latencyMs,
            attempt=payload.attempt,
            trace_id=payload.traceId,
            app_code=payload.appCode,
            conversation_id=payload.conversationId,
            error_code=payload.errorCode,
            fallback_from=payload.fallbackFrom,
            occurred_at=payload.occurredAt,
        )
        outcome = ctx.metering_ingest.ingest(event)
        results.append(
            MeteringEventResult(
                requestId=outcome.request_id,
                result=str(outcome.result),
                creditsCharged=outcome.credits_charged,
                balanceAfter=outcome.balance_after,
            )
        )
    return MeteringIngestResponse(results=results)


@router.get("/quota/summary")
async def internal_quota_summary(
    x_tenant_id: str = Header(alias="X-Tenant-Id"),
    ctx: AppContext = Depends(get_context),
) -> dict[str, object]:
    """platform 拉取真实配额数据（替换其 walletBalance=0 占位）。

    按契约 QuotaSummary 形状返回；platform 侧只做透传（不读 billing 库表）。
    """
    if not x_tenant_id:
        raise InvalidToken("缺少 X-Tenant-Id（内部调用必须显式带租户）")
    summary = ctx.quota_service.get_summary(tenant_id=x_tenant_id)
    return {
        "plan": summary.plan,
        "planBadge": summary.plan_badge,
        "walletBalance": summary.wallet_balance,
        "upgradeUrl": summary.upgrade_url,
        "usage": {
            "messagesUsed": summary.usage.messages_used,
            "tokensUsed": summary.usage.tokens_used,
        },
        "monthlyCreditGrant": summary.monthly_credit_grant,
    }


@router.put("/tenants/{tenant_id}/plan")
async def sync_plan(
    tenant_id: str,
    body: PlanSyncRequest,
    ctx: AppContext = Depends(get_context),
) -> dict[str, object]:
    """版本同步（platform 套餐变更事件 → billing 只读副本）。"""
    view = ctx.wallet_service.set_plan(tenant_id, body.plan)
    return {"tenantId": view.tenant_id, "plan": view.plan}


@router.post("/recharge/callback", response_model=PayOrderResponse)
async def payment_callback(
    body: PaymentCallbackBody,
    ctx: AppContext = Depends(get_context),
) -> PayOrderResponse:
    """支付渠道回调（验签 + 重放窗口 + 幂等入账；同订单重复回调只入账一次）。"""
    result = ctx.order_service.handle_callback(
        {"payload": body.payload, "signature": body.signature}
    )
    return PayOrderResponse(
        orderNo=result.order_no,
        credited=result.credited,
        credits=result.credits,
        balanceAfter=result.balance_after,
    )


@router.post("/reconciliation/run", response_model=ReconciliationResponse)
async def run_reconciliation(
    scope: str = "global",
    ctx: AppContext = Depends(get_context),
) -> ReconciliationResponse:
    """对账任务（Redis 流水 vs DB 明细；差异率 >0.01% 告警并冻结结算）。"""
    outcome = ctx.reconciliation_service.run(scope=scope)
    report = outcome.report
    if report.alert:
        # 资金安全事件：差异超阈值——ERROR 级日志 + 冻结结算信号（须人工复核）
        recon_logger.error(
            "recon.alert",
            scope=scope,
            run_id=outcome.run_id,
            summary=report.summary_line(),
            msg="对账差异超阈值：冻结结算并通知财务复核",
        )
    else:
        recon_logger.info(
            "recon.ok", scope=scope, run_id=outcome.run_id, summary=report.summary_line()
        )
    return ReconciliationResponse(
        runId=outcome.run_id or 0,
        scope=scope,
        streamCount=report.stream_count,
        dbCount=report.db_count,
        matched=report.matched,
        diffCount=report.diff_count,
        diffRatio=report.diff_ratio,
        alert=report.alert,
        frozenSettlement=outcome.frozen_settlement,
        missingInDb=list(report.missing_in_db),
        missingInStream=list(report.missing_in_stream),
        amountMismatch=[
            {"requestId": r, "stream": s, "db": d} for r, s, d in report.amount_mismatch
        ],
    )
