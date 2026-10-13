"""对账应用层（R-05）：Redis 事件流水 vs DB 积分明细比对任务。

运行方式：
- `POST /internal/v1/reconciliation/run`（内部端点，手动/定时触发）；
- Phase 0 同步执行（请求内跑完，结果落 reconciliation_runs 表）；
- Phase 1 迁 Celery beat 每日任务（队列：billing，docs/03 §3.2）。

告警规则（AGENTS.md 工程规范）：差异率 > 0.01% 自动告警并**冻结结算**——
本服务产出报告与告警信号（alert=True + 结构化日志 recon.alert），
冻结结算的动作由运营/财务系统订阅该信号执行（Phase 2 收益结算落地）。
"""

from __future__ import annotations

from dataclasses import dataclass

from linkai_billing.domain.ledger import LedgerEntryKind, LedgerEntryStatus
from linkai_billing.domain.ports import (
    LedgerQuery,
    MeteringEventStream,
    ReconciliationRunStore,
)
from linkai_billing.domain.reconciliation import (
    DbRecord,
    ReconciliationReport,
    StreamRecord,
    reconcile,
)


@dataclass(frozen=True)
class ReconciliationOutcome:
    report: ReconciliationReport
    run_id: int | None = None
    frozen_settlement: bool = False


class ReconciliationService:
    def __init__(
        self,
        *,
        stream: MeteringEventStream,
        ledger: LedgerQuery,
        run_store: ReconciliationRunStore,
    ) -> None:
        self._stream = stream
        self._ledger = ledger
        self._run_store = run_store

    def run(self, *, scope: str = "global") -> ReconciliationOutcome:
        """执行一次全量对账（Phase 0：全租户；按 租户:request_id 对齐双侧键）。"""
        stream_records: list[StreamRecord] = []
        for _entry_id, payload in self._stream.range_all():
            tenant_id = payload.get("tenant_id", "")
            request_id = payload.get("event_id", "")
            try:
                credits = int(payload.get("credits", "0"))
            except ValueError:
                credits = 0
            stream_records.append(
                StreamRecord(request_id=f"{tenant_id}:{request_id}", credits=credits)
            )

        db_records: list[DbRecord] = []
        for tenant_id in self._ledger.tenant_ids_with_debits():
            before: tuple[object, int] | None = None
            while True:
                rows = self._ledger.list_entries(
                    tenant_id,
                    kind=LedgerEntryKind.DEBIT,
                    limit=500,
                    before=before,  # type: ignore[arg-type]
                )
                for entry in rows:
                    db_records.append(
                        DbRecord(
                            request_id=f"{entry.tenant_id}:{entry.request_id}",
                            credits=entry.credits_charged,
                            applied=entry.status is LedgerEntryStatus.APPLIED,
                        )
                    )
                if len(rows) < 500:
                    break
                last = rows[-1]
                before = (last.occurred_at, last.row_id)

        report = reconcile(stream=stream_records, db=db_records)
        run_id = self._run_store.save(
            scope=scope,
            stream_count=report.stream_count,
            db_count=report.db_count,
            matched=report.matched,
            diff_count=report.diff_count,
            diff_ratio=report.diff_ratio,
            alert=report.alert,
            detail={
                "missing_in_db": list(report.missing_in_db)[:100],
                "missing_in_stream": list(report.missing_in_stream)[:100],
                "amount_mismatch": [
                    {"request_id": r, "stream": s, "db": d}
                    for r, s, d in report.amount_mismatch[:100]
                ],
                "blocked": report.blocked_count,
            },
        )

        # 告警日志由 api 层（框架层）负责——services 零框架 import；
        # 告警信号本身在 report.alert / frozen_settlement 上，供订阅方消费。
        return ReconciliationOutcome(
            report=report, run_id=run_id, frozen_settlement=report.alert
        )
