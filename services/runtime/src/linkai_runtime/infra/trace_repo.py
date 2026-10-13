"""执行链仓储实现（SQLAlchemy）。steps 以 JSON 快照落库（可回放、不可变）。"""

from __future__ import annotations

from datetime import UTC

from sqlalchemy.orm import Session, sessionmaker

from linkai_runtime.domain.trace import ExecutionTrace, TraceStatus
from linkai_runtime.infra.models import ExecutionTraceModel


class SqlAlchemyExecutionTraceRepository:
    """执行链仓储（实现 domain.ports.ExecutionTraceRepository 协议）。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def add(self, trace: ExecutionTrace) -> None:
        with self._session() as session:
            session.add(
                ExecutionTraceModel(
                    trace_id=trace.trace_id,
                    tenant_id=trace.tenant_id,
                    conversation_id=trace.conversation_id,
                    app_code=trace.app_code,
                    model=trace.model,
                    status=str(trace.status),
                    steps_json=[step.to_dict() for step in trace.steps],
                    created_at=trace.created_at,
                )
            )
            session.commit()

    def get(self, tenant_id: str, trace_id: str) -> ExecutionTrace | None:
        with self._session() as session:
            row = session.get(ExecutionTraceModel, trace_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            # Phase 0 回放只取索引与步骤快照原文（steps_json 即 to_dict 形态）
            return ExecutionTrace.create(
                trace_id=row.trace_id,
                tenant_id=row.tenant_id,
                conversation_id=row.conversation_id,
                app_code=row.app_code,
                model=row.model,
                steps=(),  # 快照原文经 row.steps_json 暴露；反序列化为强类型属 Phase 1
                status=_status_of(row.status),
            )

    def snapshot(self, tenant_id: str, trace_id: str) -> dict[str, object] | None:
        """取 steps JSON 原文（调试窗回放直接渲染，不重建强类型）。"""
        with self._session() as session:
            row = session.get(ExecutionTraceModel, trace_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return {
                "traceId": row.trace_id,
                "tenantId": row.tenant_id,
                "conversationId": row.conversation_id,
                "appCode": row.app_code,
                "model": row.model,
                "status": row.status,
                "steps": list(row.steps_json),
                "createdAt": row.created_at.astimezone(UTC).isoformat(),
            }


def _status_of(raw: str) -> TraceStatus:
    try:
        return TraceStatus(raw)
    except ValueError:
        return TraceStatus.OK
