"""执行链观测（trace 落库可回放）。

一次「用户消息 → 上下文装配 → 模型调用」= 一个 ExecutionTrace；
每一步 = 一个 TraceStep（kind/plugin_name/thought/plugin_input/plugin_output/
duration_ms/status/usage）。docs/observability.md §1.3：对话级 trace 可回放。

铁律：plugin_input/plugin_output 存**结构化摘要**（装配后的 messages、模型响应），
用于调试窗回放；日志禁止出现密钥（本模块不涉及凭证）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from linkai_runtime.domain.chat import TokenUsage
from linkai_runtime.domain.conversation import utcnow


class TraceStepKind(StrEnum):
    """执行链步骤类型（Phase 0：装配 + 模型调用；tool_call 为插件预留）。"""

    CONTEXT_ASSEMBLY = "context_assembly"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"


class TraceStatus(StrEnum):
    """执行链/步骤状态。"""

    OK = "ok"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class TraceStep:
    """单个执行步骤。"""

    seq: int
    kind: TraceStepKind
    plugin_name: str
    thought: str
    plugin_input: dict[str, object] = field(default_factory=dict)
    plugin_output: dict[str, object] | None = None
    duration_ms: int | None = None
    status: TraceStatus = TraceStatus.OK
    usage: TokenUsage | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "seq": self.seq,
            "kind": str(self.kind),
            "pluginName": self.plugin_name,
            "thought": self.thought,
            "pluginInput": self.plugin_input,
            "pluginOutput": self.plugin_output,
            "durationMs": self.duration_ms,
            "status": str(self.status),
        }
        if self.usage is not None:
            payload["usage"] = {
                "promptTokens": self.usage.prompt_tokens,
                "completionTokens": self.usage.completion_tokens,
                "totalTokens": self.usage.total_tokens,
                "credits": self.usage.credits,
            }
        return payload


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    """一次对话的完整执行链。"""

    trace_id: str
    tenant_id: str
    conversation_id: str
    app_code: str | None
    model: str
    steps: tuple[TraceStep, ...] = ()
    status: TraceStatus = TraceStatus.OK
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        tenant_id: str,
        conversation_id: str,
        app_code: str | None,
        model: str,
        steps: tuple[TraceStep, ...] = (),
        status: TraceStatus = TraceStatus.OK,
    ) -> ExecutionTrace:
        return cls(
            trace_id=trace_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            app_code=app_code,
            model=model,
            steps=steps,
            status=status,
            created_at=utcnow(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "traceId": self.trace_id,
            "tenantId": self.tenant_id,
            "conversationId": self.conversation_id,
            "appCode": self.app_code,
            "model": self.model,
            "status": str(self.status),
            "steps": [s.to_dict() for s in self.steps],
            "createdAt": self.created_at.isoformat(),
        }
