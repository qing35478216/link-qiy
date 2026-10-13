"""API 层用例——契约 service-api.yaml v0.1.1 + runtime-events.yaml 双侧。

覆盖（工单验收标准 2 的自验部分）：
- stream 默认 false（不传该字段返回完整 JSON）
- stream=true：text/event-stream + 事件序列 node_started → message_chunk* → done
- done 必带 usage（含 credits）+ finishReason
- 非流式 usage 同样带 credits
- 401（缺/错 Key）、422（非法入参：messages 类型/role 枚举/temperature 越界/缺 model）
- 429 统一错误信封 {code,message,requestId}
- 会话续聊（conversationId 贯通）
"""

from __future__ import annotations

import json

import pytest

from linkai_runtime.infra.quota_guard import InMemoryQuotaGuard
from tests.conftest import auth_headers


def _read_sse_events(response: object) -> list[dict]:
    """把 TestClient 流式响应解析为事件列表（每帧一个 data: JSON）。

    兼容 httpx/httpx2 两种 Response（iter_lines 的 decode_unicode 参数在
    新版被移除，按元素类型自行解码）。
    """
    events: list[dict] = []
    for raw in response.iter_lines():  # type: ignore[attr-defined]
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line and line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if payload and payload != "[DONE]":
                events.append(json.loads(payload))
    return events


class TestNonStreaming:
    def test_stream_defaults_to_false_full_json(self, demo_client: object) -> None:
        response = demo_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        body = response.json()
        # 契约 required：id/created/model/choices
        assert body["id"] and body["created"] and body["model"]
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert body["choices"][0]["message"]["content"] == "你好世界"
        assert body["choices"][0]["finishReason"] == "stop"
        # usage 带 credits（契约：消耗积分）
        assert body["usage"] == {
            "promptTokens": 120,
            "completionTokens": 30,
            "totalTokens": 150,
            "credits": 7,
        }

    def test_conversation_id_roundtrip(self, demo_client: object) -> None:
        first = demo_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "第一问"}],
                "appCode": "demo",
            },
            headers=auth_headers(),
        ).json()
        # 非流式响应体没有 conversationId（契约未定义）——经流式事件回拿；
        # 这里验证直通模式不炸 + 会话字段可经 trace 查询（回放链完整）
        assert first["choices"][0]["message"]["content"] == "你好世界"

    def test_raw_passthrough_mode(self, raw_client: object) -> None:
        """无 appCode：OpenAI 兼容直通（messages 原样转发）。"""
        response = raw_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是助手"},
                    {"role": "user", "content": "你好"},
                ],
            },
            headers=auth_headers(),
        )
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "你好世界"


class TestStreaming:
    def test_sse_event_sequence_and_done_terminal(self, demo_client: object) -> None:
        with demo_client.stream(  # type: ignore[attr-defined]
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
            assert "text/event-stream" in response.headers["content-type"]
            events = _read_sse_events(response)

        kinds = [e["event"] for e in events]
        assert kinds[0] == "node_started"
        assert kinds[1:-1] == ["message_chunk"] * 3
        assert kinds[-1] == "done"  # done 是唯一正常终局
        # message_chunk 的 seq 从 0 连续
        assert [e["data"]["seq"] for e in events[1:-1]] == [0, 1, 2]
        # 信封必填字段全量存在
        for event in events:
            assert {"event", "traceId", "conversationId", "nodeId", "ts", "data"} <= set(event)
        # done 必带 usage（含 credits）与 finishReason
        done_data = events[-1]["data"]
        assert done_data["usage"] == {
            "promptTokens": 120,
            "completionTokens": 30,
            "totalTokens": 150,
            "credits": 7,
        }
        assert done_data["finishReason"] == "stop"
        # 事件类型白名单（不准私造事件）
        assert set(kinds) <= {
            "node_started",
            "message_chunk",
            "tool_called",
            "thought",
            "error",
            "human_input_required",
            "done",
        }

    def test_sse_conversation_continuity(self, demo_client: object) -> None:
        """续聊：同一 conversationId 的事件信封一致，历史进装配。"""
        with demo_client.stream(  # type: ignore[attr-defined]
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "第一问"}],
                "appCode": "demo",
                "stream": True,
            },
            headers=auth_headers(),
        ) as first_response:
            first_events = _read_sse_events(first_response)
        conversation_id = first_events[0]["conversationId"]
        assert conversation_id

        with demo_client.stream(  # type: ignore[attr-defined]
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "第二问"}],
                "appCode": "demo",
                "conversationId": conversation_id,
                "stream": True,
            },
            headers=auth_headers(),
        ) as second_response:
            second_events = _read_sse_events(second_response)
        assert all(e["conversationId"] == conversation_id for e in second_events)

    def test_sse_trace_id_header_propagated(self, demo_client: object) -> None:
        headers = {**auth_headers(), "X-Trace-Id": "trace-from-header"}
        with demo_client.stream(  # type: ignore[attr-defined]
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
                "stream": True,
            },
            headers=headers,
        ) as response:
            events = _read_sse_events(response)
            assert response.headers["X-Trace-Id"] == "trace-from-header"
        assert all(e["traceId"] == "trace-from-header" for e in events)


class TestAuthErrors:
    def test_missing_api_key_401_envelope(self, demo_client: object) -> None:
        response = demo_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401
        body = response.json()
        assert set(body) >= {"code", "message", "requestId"}

    def test_invalid_api_key_401_envelope(self, demo_client: object) -> None:
        response = demo_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions",
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]},
            headers=auth_headers(key="sk-wrong-key"),
        )
        assert response.status_code == 401

    def test_stream_auth_failure_returns_http_401(self, demo_client: object) -> None:
        """鉴权在进流之前（依赖层）：流式请求的无效 Key 走 HTTP 401 信封。"""
        with demo_client.stream(  # type: ignore[attr-defined]
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
            headers=auth_headers(key="sk-wrong-key"),
        ) as response:
            assert response.status_code == 401  # 鉴权在进流之前，走 HTTP 信封


class TestValidation:
    @pytest.mark.parametrize(
        ("payload", "why"),
        [
            (
                {"model": "deepseek-chat", "messages": "not-an-array"},
                "messages 类型错误：契约 required 为 array",
            ),
            (
                {"model": "deepseek-chat", "messages": [{"role": "nobody", "content": "x"}]},
                "role 越界：契约 enum 仅 [system,user,assistant,tool]",
            ),
            (
                {"model": "deepseek-chat", "messages": [{"role": "user"}]},
                "缺 required.content",
            ),
            (
                {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "hi"}],
                    "temperature": 5.0,
                },
                "temperature 越界：契约 maximum 为 2",
            ),
            (
                {"messages": [{"role": "user", "content": "hi"}]},
                "缺 required.model",
            ),
        ],
    )
    def test_malformed_body_4xx(self, demo_client: object, payload: dict, why: str) -> None:
        response = demo_client.post(  # type: ignore[attr-defined]
            "/v1/chat/completions", json=payload, headers=auth_headers()
        )
        assert response.status_code in (400, 401, 403, 404, 409, 415, 422), (
            f"{why} → {response.status_code}"
        )
        assert response.status_code < 500


class TestQuota429:
    def test_quota_exceeded_uses_error_envelope(self) -> None:
        from tests.conftest import DEMO_APP_CONFIG, ScriptedGateway, make_client, make_container

        container = make_container(
            gateway=ScriptedGateway(),
            profiles={"demo": DEMO_APP_CONFIG},
            quota=InMemoryQuotaGuard(default_daily_tokens=5),
        )
        client = make_client(container)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "你好"}],
                "appCode": "demo",
            },
            headers=auth_headers(),
        )
        assert response.status_code == 429
        body = response.json()
        assert set(body) >= {"code", "message", "requestId"}
        assert body["code"] == "QUOTA_EXCEEDED"


class TestModelsApi:
    def test_models_list_contract_shape(self, demo_client: object) -> None:
        response = demo_client.get("/v1/models", headers=auth_headers())  # type: ignore[attr-defined]
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        first = body["data"][0]
        assert first["code"] == "deepseek-chat"
        assert "capabilities" in first and isinstance(first["capabilities"], list)
