"""Runtime Event 协议用例（契约 runtime-events.yaml v0.1.1）。

覆盖：七种事件的构造与信封形态（camelCase 键、必填字段）、
事件类型白名单（私造类型必须被拒）、done 的 usage/finishReason 必填语义。
"""

from __future__ import annotations

import json

from linkai_runtime.domain.chat import FinishReason, TokenUsage
from linkai_runtime.domain.errors import QuotaExceededError
from linkai_runtime.domain.events import (
    EVENT_TYPES,
    EventEnvelope,
    done,
    error,
    human_input_required,
    message_chunk,
    node_started,
    thought,
    tool_called,
)

TS = "2026-10-13T00:00:00+00:00"
TRACE = "trace-abc"
CONV = "conv-xyz"


def test_event_types_are_the_seven_contract_events() -> None:
    assert (
        frozenset(
            {
                "node_started",
                "message_chunk",
                "tool_called",
                "thought",
                "error",
                "human_input_required",
                "done",
            }
        )
        == EVENT_TYPES
    )


def test_envelope_has_contract_required_fields() -> None:
    envelope = node_started(trace_id=TRACE, conversation_id=CONV, ts=TS)
    payload = envelope.to_dict()
    assert set(payload) == {"event", "traceId", "conversationId", "nodeId", "ts", "data"}
    assert payload["event"] == "node_started"
    assert payload["nodeId"] is None
    assert json.dumps(payload, ensure_ascii=False)  # 可序列化


def test_unknown_event_type_rejected() -> None:
    """铁律：不准私造 SSE 事件类型。"""
    import pytest

    with pytest.raises(ValueError, match="未定义的事件类型"):
        EventEnvelope(
            event="my_private_event",
            trace_id=TRACE,
            conversation_id=CONV,
            ts=TS,
            node_id=None,
            data={},
        )


def test_message_chunk_requires_seq() -> None:
    envelope = message_chunk(trace_id=TRACE, conversation_id=CONV, delta="你", seq=0, ts=TS)
    assert envelope.data == {"delta": "你", "seq": 0}


def test_done_carries_usage_with_credits_and_finish_reason() -> None:
    usage = TokenUsage.of(120, 30, credits=9)
    envelope = done(
        trace_id=TRACE,
        conversation_id=CONV,
        usage=usage,
        finish_reason=FinishReason.STOP,
        ts=TS,
    )
    assert envelope.data == {
        "usage": {"promptTokens": 120, "completionTokens": 30, "totalTokens": 150, "credits": 9},
        "finishReason": "stop",
    }


def test_error_event_shape() -> None:
    envelope = error(
        trace_id=TRACE,
        conversation_id=CONV,
        code="QUOTA_EXCEEDED",
        message="配额不足",
        retriable=False,
        ts=TS,
    )
    assert envelope.data == {"code": "QUOTA_EXCEEDED", "message": "配额不足", "retriable": False}


def test_tool_called_event_shape() -> None:
    envelope = tool_called(
        trace_id=TRACE,
        conversation_id=CONV,
        plugin_name="weather",
        plugin_input={"city": "北京"},
        thought="需要查天气",
        duration_ms=120,
        ts=TS,
    )
    assert envelope.data["pluginName"] == "weather"
    assert envelope.data["pluginInput"] == {"city": "北京"}
    assert envelope.data["thought"] == "需要查天气"
    assert envelope.data["durationMs"] == 120


def test_thought_and_human_input_required_shapes() -> None:
    thought_env = thought(trace_id=TRACE, conversation_id=CONV, content="思考中", ts=TS)
    assert thought_env.data == {"content": "思考中"}
    hir_env = human_input_required(
        trace_id=TRACE, conversation_id=CONV, prompt="请确认", timeout_seconds=60, ts=TS
    )
    assert hir_env.data == {"prompt": "请确认", "timeoutSeconds": 60}


def test_domain_error_maps_to_error_event_fields() -> None:
    """QuotaExceededError → error 事件字段（services 层的映射依据）。"""
    exc = QuotaExceededError("积分不足")
    envelope = error(
        trace_id=TRACE,
        conversation_id=CONV,
        code=exc.code,
        message=str(exc),
        retriable=exc.retriable,
        ts=TS,
    )
    assert envelope.data["code"] == "QUOTA_EXCEEDED"
    assert exc.client_status == 429
