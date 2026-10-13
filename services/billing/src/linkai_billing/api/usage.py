"""使用记录路由（控制台面）：全维度流水（来源/应用/模型/Token/积分/耗时/状态）。

游标分页（契约 cursor 口径）：`nextCursor` 为空表示无更多；
筛选维度：kind / source / appCode / modelCode / since / until。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from linkai_billing.api.deps import AppContext, get_context, get_principal
from linkai_billing.api.schemas import UsagePageResponse, UsageRecordResponse
from linkai_billing.domain.auth import Principal
from linkai_billing.domain.ledger import LedgerEntryKind

router = APIRouter(prefix="/v1/usage", tags=["Usage"])


def _parse_cursor(cursor: str | None) -> tuple[datetime, int] | None:
    """解析游标（occurredAt|rowId）；非法游标返回 None（从头开始）。"""
    if not cursor:
        return None
    raw_at, _, raw_id = cursor.partition("|")
    try:
        moment = datetime.fromisoformat(raw_at)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment, int(raw_id)
    except ValueError:
        return None


@router.get("/records", response_model=UsagePageResponse)
async def list_records(
    kind: str | None = Query(default=None),
    source: str | None = Query(default=None),
    appCode: str | None = Query(default=None),
    modelCode: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> UsagePageResponse:
    page = ctx.usage_service.list_records(
        tenant_id=principal.tenant_id,
        kind=LedgerEntryKind(kind) if kind else None,
        source=source,
        app_code=appCode,
        model_code=modelCode,
        since=since,
        until=until,
        limit=limit,
        before=_parse_cursor(cursor),
    )
    return UsagePageResponse(
        items=[
            UsageRecordResponse(
                entryId=r.entry_id,
                requestId=r.request_id,
                kind=r.kind,
                source=r.source,
                status=r.status,
                delta=r.delta,
                balanceAfter=r.balance_after,
                appCode=r.app_code,
                modelCode=r.model_code,
                provider=r.provider,
                promptTokens=r.prompt_tokens,
                completionTokens=r.completion_tokens,
                totalTokens=r.total_tokens,
                creditsCharged=r.credits_charged,
                latencyMs=r.latency_ms,
                outcome=r.outcome,
                traceId=r.trace_id,
                occurredAt=r.occurred_at,
            )
            for r in page.items
        ],
        nextCursor=page.next_cursor,
    )
