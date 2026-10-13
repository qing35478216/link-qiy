"""SSE 流式用例——契约 `runtime-events.yaml` 事件序列。

关键断言：
- 事件序列必须是 `message_chunk*` → `done`（协议约定的正常终局）；
- `done` 必带 usage（含 credits）与 finishReason；
- 异常终局是 `error` 事件，消费端不依赖连接关闭。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import FastAPI

from linkai_model_proxy.api.app import create_app
from linkai_model_proxy.api.dependencies import get_container
from linkai_model_proxy.domain.errors import ProviderCallError
from linkai_model_proxy.domain.fallback import FallbackPlanner, RetryPolicy
from linkai_model_proxy.domain.invocation import FinishReason, StreamDelta, TokenUsage
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.domain.routing import ModelInvocationService
from linkai_model_proxy.infra.adapters import OpenAIAdapter
from linkai_model_proxy.infra.memory import (
    HeuristicTokenEstimator,
    InMemoryTelemetrySink,
)
from linkai_model_proxy.services.gateway import ModelGatewayService
from linkai_model_proxy.services.playground import PlaygroundService
from tests.conftest import TENANT
from tests.integration.test_api import HEADERS, build_test_container


class ScriptedStreamAdapter(OpenAIAdapter):
    """可控的流式适配器——按模式吐分片或抛错。"""

    def __init__(self, http: Any, mode: str) -> None:
        self._mode = mode
        self._provider = "openai"

    @property
    def provider(self) -> str:
        return self._provider

    async def stream(
        self, request: Any, *, card: Any, credential: Any
    ) -> AsyncIterator[StreamDelta]:
        if self._mode == "fail_before_any_chunk":
            raise ProviderCallError("503 upstream down")
        yield StreamDelta(delta="你", seq=0)
        if self._mode == "fail_midway":
            raise ProviderCallError("连接中断")
        yield StreamDelta(delta="好", seq=1)
        yield StreamDelta(
            delta="", seq=2, finish_reason=FinishReason.STOP, usage=TokenUsage.of(120, 30)
        )

    async def complete(self, request: Any, *, card: Any, credential: Any) -> Any:
        raise ProviderCallError("非流式未接入", retriable=False)


def build_stream_app(mode: str) -> tuple[FastAPI, InMemoryTelemetrySink]:
    """装配一个 openai 走脚本化流式适配器的应用。"""
    telemetry = InMemoryTelemetrySink()
    container = build_test_container(telemetry)

    registry = AdapterRegistry()
    for provider, registration in container.registry.snapshot().items():
        if provider == "openai":
            registry.register(
                provider,
                lambda: ScriptedStreamAdapter(container.http, mode),
                capabilities=registration.capabilities,
            )
        else:
            registry.register(
                provider,
                registration.factory,
                capabilities=registration.capabilities,
            )

    invoker = ModelInvocationService(
        registry=registry,
        catalog=container.catalog,
        credentials=container.credentials,
        telemetry=telemetry,
        estimator=HeuristicTokenEstimator(),
        # 关闭降级链，聚焦流式协议本身
        planner=FallbackPlanner(policy=RetryPolicy(max_attempts=1, honor_fallback_chain=False)),
    )
    gateway = ModelGatewayService(invoker)
    container.registry = registry
    container.invoker = invoker
    container.gateway = gateway
    container.playground = PlaygroundService(gateway)

    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    return app, telemetry


async def _post_stream(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )


def _parse_sse(text: str) -> list[dict[str, Any]]:
    """解析 SSE 文本为事件列表。"""
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


class TestStreamHappyPath:
    async def test_event_sequence(self) -> None:
        app, _ = build_stream_app("ok")
        response = await _post_stream(app)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(response.text)
        names = [e["event"] for e in events]
        assert names[0] == "message_chunk"
        assert names[-1] == "done"
        assert "error" not in names

    async def test_done_carries_usage_with_credits(self) -> None:
        app, _ = build_stream_app("ok")
        response = await _post_stream(app)
        done = _parse_sse(response.text)[-1]
        usage = done["data"]["usage"]
        # 契约 DoneEvent.data.usage 四个字段必填
        for field in ("promptTokens", "completionTokens", "totalTokens", "credits"):
            assert field in usage
        assert usage["credits"] > 0
        assert done["data"]["finishReason"] == "stop"

    async def test_envelope_required_fields_present(self) -> None:
        app, _ = build_stream_app("ok")
        response = await _post_stream(app)
        for event in _parse_sse(response.text):
            # 契约 EventEnvelope required: event/traceId/conversationId/ts
            for field in ("event", "traceId", "conversationId", "ts"):
                assert field in event, f"事件信封缺 {field}"

    async def test_message_chunk_seq_monotonic(self) -> None:
        """消费端按 seq 排序兜底乱序——必须单调递增。"""
        app, _ = build_stream_app("ok")
        response = await _post_stream(app)
        seqs = [
            e["data"]["seq"] for e in _parse_sse(response.text) if e["event"] == "message_chunk"
        ]
        assert seqs == sorted(seqs)
        assert seqs[0] == 0

    async def test_metering_emitted_for_stream(self) -> None:
        """流式同样必须计量（红���：不准绕过计量）。"""
        app, telemetry = build_stream_app("ok")
        await _post_stream(app)
        assert len(telemetry.events) == 1
        event = telemetry.events[0]
        assert event.tenant_id == TENANT
        assert event.prompt_tokens == 120
        assert event.completion_tokens == 30
        assert event.credits > 0

    async def test_nginx_buffering_disabled(self) -> None:
        """反代缓冲会让 SSE 退化成非流式——必须显式关掉。"""
        app, _ = build_stream_app("ok")
        response = await _post_stream(app)
        assert response.headers["X-Accel-Buffering"] == "no"
        assert response.headers["Cache-Control"] == "no-cache"


class TestStreamErrorPaths:
    async def test_error_before_first_chunk(self) -> None:
        app, _ = build_stream_app("fail_before_any_chunk")
        response = await _post_stream(app)
        events = _parse_sse(response.text)
        names = [e["event"] for e in events]
        assert "error" in names
        error = next(e for e in events if e["event"] == "error")
        assert error["data"]["code"]
        assert "retriable" in error["data"]
        # 异常终局不得再发 done
        assert "done" not in names

    async def test_error_midway_no_done(self) -> None:
        """已吐内容后失败：终局是 error，且不能出现 done。"""
        app, _ = build_stream_app("fail_midway")
        response = await _post_stream(app)
        events = _parse_sse(response.text)
        names = [e["event"] for e in events]
        assert names[0] == "message_chunk"
        assert "error" in names
        assert "done" not in names

    async def test_metering_emitted_even_on_stream_failure(self) -> None:
        """失败也计量——对账与厂商成本核算需要。"""
        app, telemetry = build_stream_app("fail_midway")
        await _post_stream(app)
        assert telemetry.events, "流式失败必须留计量痕迹"
        assert all(e.credits == 0 for e in telemetry.events)
