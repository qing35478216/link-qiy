"""端到端 mock 链路（工单自验项：端到端 mock 链路 + 首 token 延迟基线）。

真 HTTP 栈：TestClient → ChatService → HttpModelGateway（httpx）
→ respx mock 的 model-proxy /v1/chat/completions（流式 SSE + 非流式 JSON）
→ SQLite 落库。验证 infra 客户端（SSE 解析/错误映射/头注入）与全链路贯通。

TTFT（Time To First Token）：测量"请求发出 → 首个 message_chunk 事件"的
延迟，P50/P99 打印进报告（mock 上游带 30ms 首片延迟模拟模型生成时间；
运行时本身开销为 ASGI + 装配 + 上游首跳，不含真实厂商网络）。
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx
import pytest
import respx

from tests.conftest import DEMO_APP_CONFIG, auth_headers

MODEL_PROXY_BASE = "http://model-proxy.test"


def _sse_body(chunks: tuple[str, ...], *, usage: dict[str, object]) -> str:
    frames = [
        json.dumps(
            {
                "event": "message_chunk",
                "traceId": "t",
                "conversationId": "c",
                "nodeId": None,
                "ts": "2026-10-13T00:00:00+00:00",
                "data": {"delta": chunk, "seq": index},
            },
            ensure_ascii=False,
        )
        for index, chunk in enumerate(chunks)
    ]
    frames.append(
        json.dumps(
            {
                "event": "done",
                "traceId": "t",
                "conversationId": "c",
                "nodeId": None,
                "ts": "2026-10-13T00:00:00+00:00",
                "data": {"usage": usage, "finishReason": "stop"},
            },
            ensure_ascii=False,
        )
    )
    return "".join(f"data: {frame}\n\n" for frame in frames)


def _mock_proxy_stream(chunks: tuple[str, ...] = ("你", "好", "世界")) -> None:
    usage = {"promptTokens": 120, "completionTokens": 30, "totalTokens": 150, "credits": 7}
    respx.post(f"{MODEL_PROXY_BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=_sse_body(chunks, usage=usage).encode("utf-8"),
        )
    )


def _mock_proxy_complete() -> None:
    body = {
        "id": "cmpl-e2e-0001",
        "created": 1_700_000_000,
        "model": "deepseek-chat",
        "usage": {"promptTokens": 120, "completionTokens": 30, "totalTokens": 150, "credits": 7},
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "你好世界"},
                "finishReason": "stop",
            }
        ],
    }
    respx.post(f"{MODEL_PROXY_BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=body)
    )


@pytest.fixture
def e2e_client() -> Iterator[object]:
    """真 HttpModelGateway + respx + SQLite 的端到端客户端。"""
    from linkai_runtime.infra.model_proxy_client import HttpModelGateway
    from tests.conftest import make_client, make_container, make_settings

    settings = make_settings(model_proxy_base_url=MODEL_PROXY_BASE)
    container = make_container(
        gateway=HttpModelGateway(MODEL_PROXY_BASE, timeout_seconds=5.0),
        profiles={"demo": DEMO_APP_CONFIG},
        settings=settings,
    )
    client = make_client(container)
    with client:  # type: ignore[attr-defined]
        yield client


def _read_sse_events(response: object) -> list[dict]:
    events: list[dict] = []
    for raw in response.iter_lines():  # type: ignore[attr-defined]
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line and line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if payload and payload != "[DONE]":
                events.append(json.loads(payload))
    return events


class TestEndToEndMockChain:
    @respx.mock
    def test_non_stream_full_chain(self, e2e_client: object) -> None:
        _mock_proxy_complete()
        response = e2e_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "cmpl-e2e-0001"
        assert body["choices"][0]["message"]["content"] == "你好世界"
        assert body["usage"]["credits"] == 7
        # 上游收到的身份头（X-Tenant-Id / X-Trace-Id）已注入
        sent = respx.calls.last.request
        assert sent.headers["X-Tenant-Id"] == "t-001"
        assert sent.headers["X-Trace-Id"]

    @respx.mock
    def test_stream_full_chain(self, e2e_client: object) -> None:
        _mock_proxy_stream()
        with e2e_client.stream(  # type: ignore[attr-defined]
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
                "stream": True,
            },
            headers=auth_headers(),
        ) as response:
            assert response.status_code == 200
            events = _read_sse_events(response)
        kinds = [e["event"] for e in events]
        assert kinds == ["node_started", "message_chunk", "message_chunk", "message_chunk", "done"]
        assert "".join(e["data"]["delta"] for e in events[1:-1]) == "你好世界"
        assert events[-1]["data"]["usage"]["credits"] == 7

    @respx.mock
    def test_upstream_5xx_maps_to_error_event(self, e2e_client: object) -> None:
        respx.post(f"{MODEL_PROXY_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(
                503, json={"code": "PROVIDER_UNAVAILABLE", "message": "down"}
            )
        )
        with e2e_client.stream(  # type: ignore[attr-defined]
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
                "stream": True,
            },
            headers=auth_headers(),
        ) as response:
            events = _read_sse_events(response)
        assert events[-1]["event"] == "error"
        assert events[-1]["data"]["code"] == "MODEL_UPSTREAM_ERROR"
        assert events[-1]["data"]["retriable"] is True

    @respx.mock
    def test_upstream_429_maps_to_quota_http(self, e2e_client: object) -> None:
        respx.post(f"{MODEL_PROXY_BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(429, json={"code": "QUOTA_EXCEEDED", "message": "积分不足"})
        )
        response = e2e_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
            },
            headers=auth_headers(),
        )
        assert response.status_code == 429
        assert response.json()["code"] == "QUOTA_EXCEEDED"


class TestTimeToFirstToken:
    """首 token 延迟基线（P50/P99，mock 上游）。"""

    @respx.mock
    def test_ttft_p50_p99(self, e2e_client: object) -> None:
        _mock_proxy_stream()
        samples: list[float] = []
        for _ in range(30):
            started = time.monotonic()  # 请求发出前起表（含 ASGI 分发 + 装配 + 上游首跳）
            with e2e_client.stream(  # type: ignore[attr-defined]
                "POST",
                "/v1/chat/completions",
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "你好"}],
                    "appCode": "demo",
                    "stream": True,
                },
                headers=auth_headers(),
            ) as response:
                for event in _read_sse_events(response):
                    if event.get("event") == "message_chunk":
                        samples.append((time.monotonic() - started) * 1000)
                        break
        assert len(samples) == 30
        samples.sort()
        p50 = samples[len(samples) // 2]
        p99 = samples[min(len(samples) - 1, int(len(samples) * 0.99))]
        print(f"\n[TTFT] n=30 P50={p50:.1f}ms P99={p99:.1f}ms max={samples[-1]:.1f}ms")
        # 运行时链路开销基线（mock 上游，无真实网络）：P99 必须 < 1s
        assert p99 < 1000, f"TTFT P99 {p99:.1f}ms 超出 1s 预算（mock 链路）"
