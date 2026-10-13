"""五家厂商适配器的回放用例——验收标准 1。

全部用 `respx` 回放，**不触网**（conftest 的 autouse 护栏双保险）。
每家厂商都验证：非流式解析正确 + 流式分片与终局 usage 正确。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from linkai_model_proxy.domain.adapter import ProviderCredential
from linkai_model_proxy.domain.errors import (
    ProviderCallError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatRequest,
    FinishReason,
    MessageRole,
)
from linkai_model_proxy.infra.adapters import (
    AnthropicAdapter,
    DeepSeekAdapter,
    OpenAIAdapter,
    QwenAdapter,
    ZhipuGlmAdapter,
)
from linkai_model_proxy.infra.http_client import VendorHttpClient
from linkai_model_proxy.infra.ssrf import SsrfViolation

from tests.conftest import make_card

CREDENTIAL = ProviderCredential(provider="test", secret="sk-unit-test-key-123456")


def _request(*, system: bool = False) -> ChatRequest:
    messages = [ChatMessage(role=MessageRole.USER, content="你好")]
    if system:
        messages.insert(0, ChatMessage(role=MessageRole.SYSTEM, content="你是助手"))
    # model 只用于网关侧路由，适配器层用 card.code，故给个占位非空值
    return ChatRequest(model="placeholder-model", messages=tuple(messages))


def _sse(*frames: dict[str, object]) -> str:
    """把帧序列拼成 SSE 文本（data帧必须是合法 JSON）。"""
    lines = [f"data: {json.dumps(frame, ensure_ascii=False)}" for frame in frames]
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


# ---------- OpenAI 兼容四家共用响应形态 ----------


class _OpenAICompatCase:
    """OpenAI 兼容四家（OpenAI / DeepSeek / Qwen / GLM）的共用断言。"""

    adapter_class: type
    host: str
    model: str
    #: 厂商 base_url 里的路径前缀（Qwen/GLM 有兼容模式路径）
    base_path: str = ""

    def _adapter(self, http: VendorHttpClient) -> object:
        return self.adapter_class(http)

    def _chat_url(self) -> str:
        return f"https://{self.host}{self.base_path}/chat/completions"

    async def test_non_stream_completion(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x", enabled=True)
        body = {
            "id": "chatcmpl-1",
            "created": 1_700_000_000,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "你好呀"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13},
        }
        with respx.mock:
            route = respx.post(self._chat_url()).mock(
                return_value=httpx.Response(200, json=body)
            )
            response = await adapter.complete(  # type: ignore[attr-defined]
                _request(system=True), card=card, credential=CREDENTIAL
            )
        assert route.called
        assert response.content == "你好呀"
        assert response.usage.prompt_tokens == 9
        assert response.usage.completion_tokens == 4
        assert response.choices[0].finish_reason is FinishReason.STOP

    async def test_request_carries_openai_shape_and_bearer(
        self, vendor_http: VendorHttpClient
    ) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x")
        body = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        with respx.mock:
            route = respx.post(self._chat_url()).mock(return_value=httpx.Response(200, json=body))
            await adapter.complete(  # type: ignore[attr-defined]
                _request(), card=card, credential=CREDENTIAL
            )
        sent = route.calls[0].request
        assert sent.headers["authorization"] == f"Bearer {CREDENTIAL.secret}"
        payload = json.loads(sent.content)
        assert payload["model"] == self.model
        assert payload["messages"][0] == {"role": "user", "content": "你好"}

    async def test_stream_yields_terminal_delta_with_usage(
        self, vendor_http: VendorHttpClient
    ) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x")
        frames = (
            {"choices": [{"delta": {"content": "你"}}]},
            {"choices": [{"delta": {"content": "好"}}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )
        with respx.mock:
            respx.post(self._chat_url()).mock(return_value=httpx.Response(200, text=_sse(*frames)))
            deltas = [
                d
                async for d in adapter.stream(  # type: ignore[attr-defined]
                    _request(), card=card, credential=CREDENTIAL
                )
            ]
        # 末帧choices 为空但带 usage ——必须仍产出终局分片，否则计量会缺数
        assert [d.delta for d in deltas] == ["你", "好", ""]
        assert deltas[-1].is_terminal
        assert deltas[-1].usage is not None
        assert deltas[-1].usage.prompt_tokens == 5
        assert deltas[-1].usage.completion_tokens == 2

    async def test_rate_limit_maps_to_retriable_error(
        self, vendor_http: VendorHttpClient
    ) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x")
        with respx.mock:
            respx.post(self._chat_url()).mock(
                return_value=httpx.Response(429, json={"error": "rate limited"})
            )
            with pytest.raises(ProviderRateLimitedError):
                await adapter.complete(  # type: ignore[attr-defined]
                    _request(), card=card, credential=CREDENTIAL
                )

    async def test_server_error_maps_to_unavailable(
        self, vendor_http: VendorHttpClient
    ) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x")
        with respx.mock:
            respx.post(self._chat_url()).mock(
                return_value=httpx.Response(503, text="upstream down")
            )
            with pytest.raises(ProviderUnavailableError):
                await adapter.complete(  # type: ignore[attr-defined]
                    _request(), card=card, credential=CREDENTIAL
                )

    async def test_bad_request_is_not_retriable(self, vendor_http: VendorHttpClient) -> None:
        """4xx 语义错误不可降级——换模型也解决不了。"""
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x")
        with respx.mock:
            respx.post(self._chat_url()).mock(
                return_value=httpx.Response(400, json={"error": "bad model"})
            )
            with pytest.raises(ProviderCallError) as exc:
                await adapter.complete(  # type: ignore[attr-defined]
                    _request(), card=card, credential=CREDENTIAL
                )
        assert exc.value.retriable is False

    async def test_malformed_choices_raises(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code=self.model, provider="x")
        with respx.mock:
            respx.post(self._chat_url()).mock(
                return_value=httpx.Response(200, json={"choices": []})
            )
            with pytest.raises(ProviderCallError, match="choices"):
                await adapter.complete(  # type: ignore[attr-defined]
                    _request(), card=card, credential=CREDENTIAL
                )


class TestOpenAIAdapter(_OpenAICompatCase):
    adapter_class = OpenAIAdapter
    host = "api.openai.com"
    base_path = "/v1"
    model = "gpt-4o"


class TestDeepSeekAdapter(_OpenAICompatCase):
    adapter_class = DeepSeekAdapter
    host = "api.deepseek.com"
    base_path = "/v1"
    model = "deepseek-chat"


class TestQwenAdapter(_OpenAICompatCase):
    adapter_class = QwenAdapter
    host = "dashscope.aliyuncs.com"
    base_path = "/compatible-mode/v1"
    model = "qwen-plus"


class TestGlmAdapter(_OpenAICompatCase):
    adapter_class = ZhipuGlmAdapter
    host = "open.bigmodel.cn"
    base_path = "/api/paas/v4"
    model = "glm-4-flash"


class TestDeepSeekSpecifics:
    async def test_reasoner_drops_sampling_params(self, vendor_http: VendorHttpClient) -> None:
        """deepseek-reasoner 不接受 temperature/max_tokens——适配器需剔除。"""
        adapter = DeepSeekAdapter(vendor_http)
        card = make_card(code="deepseek-reasoner", provider="deepseek")
        request = ChatRequest(
            model="deepseek-reasoner",
            messages=(ChatMessage(role=MessageRole.USER, content="推理"),),
            temperature=0.7,
            max_tokens=100,
        )
        payload = adapter.build_payload(request, card)
        assert "temperature" not in payload
        assert "max_tokens" not in payload

    async def test_chat_model_keeps_sampling_params(self, vendor_http: VendorHttpClient) -> None:
        adapter = DeepSeekAdapter(vendor_http)
        card = make_card(code="deepseek-chat", provider="deepseek")
        request = ChatRequest(
            model="deepseek-chat",
            messages=(ChatMessage(role=MessageRole.USER, content="hi"),),
            temperature=0.3,
            max_tokens=64,
        )
        payload = adapter.build_payload(request, card)
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 64


# ---------- Anthropic：协议形态不同，单独一套断言 ----------


class TestAnthropicAdapter:
    def _adapter(self, http: VendorHttpClient) -> AnthropicAdapter:
        return AnthropicAdapter(http)

    def test_system_promoted_to_toplevel(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code="claude-sonnet-4", provider="anthropic")
        payload = adapter.build_payload(_request(system=True), card)
        assert payload["system"] == "你是助手"
        assert all(m["role"] != "system" for m in payload["messages"])
        assert payload["max_tokens"] == 1024  # Anthropic 必填项由默认值兜底

    def test_max_tokens_passed_through(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code="claude-sonnet-4", provider="anthropic")
        request = ChatRequest(
            model="claude-sonnet-4",
            messages=(ChatMessage(role=MessageRole.USER, content="hi"),),
            max_tokens=256,
        )
        assert adapter.build_payload(request, card)["max_tokens"] == 256

    def test_auth_headers(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        headers = adapter.build_headers(CREDENTIAL)
        assert headers["x-api-key"] == CREDENTIAL.secret
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers

    async def test_non_stream_parses_content_blocks(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code="claude-sonnet-4", provider="anthropic")
        body = {
            "id": "msg_1",
            "model": "claude-sonnet-4",
            "content": [
                {"type": "text", "text": "你好"},
                {"type": "text", "text": "世界"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 7},
        }
        with respx.mock:
            route = respx.post("https://api.anthropic.com/v1/messages").mock(
                return_value=httpx.Response(200, json=body)
            )
            response = await adapter.complete(_request(), card=card, credential=CREDENTIAL)
        assert route.called
        assert response.content == "你好世界"
        assert response.usage.prompt_tokens == 12
        assert response.usage.completion_tokens == 7
        assert response.usage.total_tokens == 19
        assert response.choices[0].finish_reason is FinishReason.STOP

    async def test_stop_reason_mapping(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code="claude-sonnet-4", provider="anthropic")
        for raw, expected in (
            ("max_tokens", FinishReason.LENGTH),
            ("tool_use", FinishReason.TOOL_CALLS),
            ("end_turn", FinishReason.STOP),
            (None, FinishReason.STOP),
        ):
            body = {
                "content": [{"type": "text", "text": "x"}],
                "stop_reason": raw,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
            with respx.mock:
                respx.post("https://api.anthropic.com/v1/messages").mock(
                    return_value=httpx.Response(200, json=body)
                )
                response = await adapter.complete(_request(), card=card, credential=CREDENTIAL)
            assert response.choices[0].finish_reason is expected

    async def test_stream_maps_event_types(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code="claude-sonnet-4", provider="anthropic")
        frames = (
            {"type": "message_start", "message": {"id": "msg_1"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "你"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "好"}},
            {"type": "ping"},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
             "usage": {"input_tokens": 8, "output_tokens": 3}},
        )
        with respx.mock:
            respx.post("https://api.anthropic.com/v1/messages").mock(
                return_value=httpx.Response(200, text=_sse(*frames))
            )
            deltas = [d async for d in adapter.stream(_request(), card=card, credential=CREDENTIAL)]
        # message_start / ping 无增量价值，被跳过
        assert [d.delta for d in deltas] == ["你", "好", ""]
        assert deltas[-1].is_terminal
        assert deltas[-1].usage is not None
        assert deltas[-1].usage.prompt_tokens == 8

    async def test_empty_content_raises(self, vendor_http: VendorHttpClient) -> None:
        adapter = self._adapter(vendor_http)
        card = make_card(code="claude-sonnet-4", provider="anthropic")
        with respx.mock:
            respx.post("https://api.anthropic.com/v1/messages").mock(
                return_value=httpx.Response(200, json={"content": []})
            )
            with pytest.raises(ProviderCallError, match="content"):
                await adapter.complete(_request(), card=card, credential=CREDENTIAL)


class TestCredentialSafety:
    def test_fingerprint_never_leaks_secret(self) -> None:
        secret = "sk-super-secret-value-9999"
        cred = ProviderCredential(provider="openai", secret=secret)
        assert secret not in cred.fingerprint()
        assert cred.fingerprint().endswith("9999")

    def test_short_secret_fully_masked(self) -> None:
        cred = ProviderCredential(provider="x", secret="short")
        assert cred.fingerprint() == "****"
        assert "short" not in cred.fingerprint()

    async def test_ssrf_blocks_internal_url(self, vendor_http: VendorHttpClient) -> None:
        """厂商 base_url 指向内网时必须被 SSRF 闸门拦下（铁律 5）。"""
        adapter = OpenAIAdapter(vendor_http)
        card = make_card(code="gpt-4o", provider="openai")
        evil = ProviderCredential(provider="openai", secret="sk-x", base_url="http://127.0.0.1:8080")
        with pytest.raises(ProviderCallError) as exc:
            await adapter.complete(_request(), card=card, credential=evil)
        assert exc.value.retriable is False

    def test_ssrf_policy_rejects_http(self) -> None:
        from linkai_model_proxy.infra.ssrf import SsrfPolicy

        policy = SsrfPolicy(allowed_hosts=frozenset({"api.openai.com"}))
        with pytest.raises(SsrfViolation, match="https"):
            policy.validate_url("http://api.openai.com/v1/chat/completions")

    def test_ssrf_policy_rejects_metadata_endpoint(self) -> None:
        from linkai_model_proxy.infra.ssrf import SsrfPolicy

        policy = SsrfPolicy(allowed_hosts=frozenset({"169.254.169.254"}))
        with pytest.raises(SsrfViolation, match="元数据"):
            policy.validate_url("https://169.254.169.254/latest/meta-data/")