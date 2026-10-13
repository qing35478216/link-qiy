"""使用记录应用层：全维度流水查询（来源/应用/模型/Token/积分/耗时/状态）。

游标分页（契约 cursor 口径）：keyset on (occurred_at, entry_id)，
`nextCursor` 为空表示无更多。导出（CSV）走同一查询路径——
Phase 0 返回结构化数据，文件流由 api 层渲染（大数据量导出 Phase 1 异步）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from linkai_billing.domain.ledger import LedgerEntry, LedgerEntryKind
from linkai_billing.domain.ports import LedgerQuery


@dataclass(frozen=True)
class UsageRecordView:
    entry_id: str
    request_id: str
    kind: str
    source: str
    status: str
    delta: int
    balance_after: int | None
    app_code: str | None
    model_code: str | None
    provider: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    credits_charged: int
    latency_ms: int
    outcome: str | None
    trace_id: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class UsagePage:
    items: list[UsageRecordView]
    next_cursor: str | None


def _view(entry: LedgerEntry) -> UsageRecordView:
    return UsageRecordView(
        entry_id=entry.entry_id,
        request_id=entry.request_id,
        kind=str(entry.kind),
        source=str(entry.source),
        status=str(entry.status),
        delta=entry.delta,
        balance_after=entry.balance_after,
        app_code=entry.app_code,
        model_code=entry.model_code,
        provider=entry.provider,
        prompt_tokens=entry.prompt_tokens,
        completion_tokens=entry.completion_tokens,
        total_tokens=entry.total_tokens,
        credits_charged=entry.credits_charged,
        latency_ms=entry.latency_ms,
        outcome=entry.outcome,
        trace_id=entry.trace_id,
        occurred_at=entry.occurred_at,
    )


class UsageService:
    def __init__(self, *, ledger: LedgerQuery) -> None:
        self._ledger = ledger

    def list_records(
        self,
        *,
        tenant_id: str,
        kind: LedgerEntryKind | None = None,
        source: str | None = None,
        app_code: str | None = None,
        model_code: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        before: tuple[datetime, int] | None = None,
    ) -> UsagePage:
        rows = self._ledger.list_entries(
            tenant_id,
            kind=kind,
            source=source,
            app_code=app_code,
            model_code=model_code,
            since=since,
            until=until,
            limit=limit,
            before=before,
        )
        items = [_view(r) for r in rows]
        next_cursor: str | None = None
        if len(rows) == limit and rows:
            last = rows[-1]
            next_cursor = f"{last.occurred_at.isoformat()}|{last.row_id}"
        return UsagePage(items=items, next_cursor=next_cursor)
