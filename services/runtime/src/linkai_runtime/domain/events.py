"""Runtime Event 协议——`packages/contracts/openapi/runtime-events.yaml` v0.1.1 的领域实现。

铁律：事件类型只增不改；不准为单个场景私造事件类型（api 层 SSE 帧是唯一出口）。
七种事件：node_started / message_chunk / tool_called / thought / error /
human_input_required / done（终局，携带 usage + finishReason）。

本模块只构造**事件对象**（纯数据，可单测）；SSE 帧序列化在 api 层。
`ts` 可注入——装配函数与事件构造都保持"输入确定则输出确定"的可测性。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from linkai_runtime.domain.chat import FinishReason, TokenUsage

# ── 事件类型常量（与契约 discriminator mapping 严格一致）─────────────
EVENT_NODE_STARTED = "node_started"
EVENT_MESSAGE_CHUNK = "message_chunk"
EVENT_TOOL_CALLED = "tool_called"
EVENT_THOUGHT = "thought"
EVENT_ERROR = "error"
EVENT_HUMAN_INPUT_REQUIRED = "human_input_required"
EVENT_DONE = "done"

#: 协议全部事件类型（消费端可据此做白名单校验；新增必须同步契约与全部消费端）
EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_NODE_STARTED,
        EVENT_MESSAGE_CHUNK,
        EVENT_TOOL_CALLED,
        EVENT_THOUGHT,
        EVENT_ERROR,
        EVENT_HUMAN_INPUT_REQUIRED,
        EVENT_DONE,
    }
)


def iso_now() -> str:
    """当前 UTC 时间（ISO8601）。协议 ts 字段格式。"""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """事件信封（契约 `EventEnvelope`：event/traceId/conversationId/nodeId/ts + data）。"""

    event: str
    trace_id: str
    conversation_id: str
    ts: str
    node_id: str | None
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.event not in EVENT_TYPES:
            raise ValueError(f"未定义的事件类型 {self.event!r}（契约只增不改，禁止私造）")

    def to_dict(self) -> dict[str, object]:
        """转契约 JSON 形态（camelCase 键）。"""
        return {
            "event": self.event,
            "traceId": self.trace_id,
            "conversationId": self.conversation_id,
            "nodeId": self.node_id,
            "ts": self.ts,
            "data": dict(self.data),
        }


def usage_to_dict(usage: TokenUsage) -> dict[str, object]:
    """契约 usage 形态（done 事件 / 非流式响应共用）。"""
    return {
        "promptTokens": usage.prompt_tokens,
        "completionTokens": usage.completion_tokens,
        "totalTokens": usage.total_tokens,
        "credits": usage.credits,
    }


# ── 事件构造器（每个返回一个信封；trace/conversation 全事件必带）────────


def node_started(
    *,
    trace_id: str,
    conversation_id: str,
    node_type: str = "llm",
    node_name: str = "",
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event=EVENT_NODE_STARTED,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data={"nodeType": node_type, "nodeName": node_name},
    )


def message_chunk(
    *,
    trace_id: str,
    conversation_id: str,
    delta: str,
    seq: int,
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    """增量分片。seq 从 0 起必填（消费方按 seq 排序兜底乱序）。"""
    return EventEnvelope(
        event=EVENT_MESSAGE_CHUNK,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data={"delta": delta, "seq": seq},
    )


def tool_called(
    *,
    trace_id: str,
    conversation_id: str,
    plugin_name: str,
    plugin_input: Mapping[str, object],
    thought: str | None = None,
    plugin_output: Mapping[str, object] | None = None,
    duration_ms: int | None = None,
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    data: dict[str, object] = {"pluginName": plugin_name, "pluginInput": dict(plugin_input)}
    if thought is not None:
        data["thought"] = thought
    if plugin_output is not None:
        data["pluginOutput"] = dict(plugin_output)
    if duration_ms is not None:
        data["durationMs"] = duration_ms
    return EventEnvelope(
        event=EVENT_TOOL_CALLED,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data=data,
    )


def thought(
    *,
    trace_id: str,
    conversation_id: str,
    content: str,
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event=EVENT_THOUGHT,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data={"content": content},
    )


def done(
    *,
    trace_id: str,
    conversation_id: str,
    usage: TokenUsage,
    finish_reason: FinishReason | str = FinishReason.STOP,
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    """正常终局事件：必带 usage（含 credits）与 finishReason。"""
    return EventEnvelope(
        event=EVENT_DONE,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data={"usage": usage_to_dict(usage), "finishReason": str(finish_reason)},
    )


def error(
    *,
    trace_id: str,
    conversation_id: str,
    code: str,
    message: str,
    retriable: bool = False,
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    """异常终局事件（消费端不依赖连接关闭）。"""
    return EventEnvelope(
        event=EVENT_ERROR,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data={"code": code, "message": message, "retriable": retriable},
    )


def human_input_required(
    *,
    trace_id: str,
    conversation_id: str,
    prompt: str,
    timeout_seconds: int | None = None,
    ts: str | None = None,
    node_id: str | None = None,
) -> EventEnvelope:
    data: dict[str, object] = {"prompt": prompt}
    if timeout_seconds is not None:
        data["timeoutSeconds"] = timeout_seconds
    return EventEnvelope(
        event=EVENT_HUMAN_INPUT_REQUIRED,
        trace_id=trace_id,
        conversation_id=conversation_id,
        ts=ts or iso_now(),
        node_id=node_id,
        data=data,
    )
