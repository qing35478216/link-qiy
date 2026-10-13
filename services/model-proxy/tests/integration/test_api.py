"""API 集成用例——端点契约、鉴权、SSRF 边界、Playground。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from linkai_model_proxy.api.app import create_app
from linkai_model_proxy.api.dependencies import AppContainer, build_container, get_container
from linkai_model_proxy.domain.adapter import AdapterCapabilities
from linkai_model_proxy.domain.errors import ProviderCallError
from linkai_model_proxy.domain.fallback import FallbackPlanner, RetryPolicy
from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatResponse,
    Choice,
    FinishReason,
    MessageRole,
    TokenUsage,
)
from linkai_model_proxy.domain.model_card import ModelCard
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.domain.routing import ModelInvocationService
from linkai_model_proxy.infra.adapters import OpenAIAdapter
from linkai_model_proxy.infra.http_client import VendorHttpClient
from linkai_model_proxy.infra.memory import (
    HeuristicTokenEstimator,
    InMemoryCredentialStore,
    InMemoryTelemetrySink,
)
from linkai_model_proxy.infra.ssrf import SsrfPolicy
from linkai_model_proxy.services.gateway import ModelGatewayService
from linkai_model_proxy.services.playground import PlaygroundService
from tests.conftest import TENANT

HEADERS = {"X-Tenant-Id": TENANT, "X-Trace-Id": "trace-integration"}
PROVIDERS = ("openai", "anthropic", "deepseek", "qwen", "glm")


class EchoAdapter(OpenAIAdapter):
    """确定性假适配器——回显模型编码，不触网。

    保留 OpenAI 适配器的 `capabilities` 声明，因此健康检查断言仍然真实。
    """

    def __init__(self, provider: str, http: VendorHttpClient) -> None:
        super().__init__(http)
        self._provider = provider

    @property
    def provider(self) -> str:
        return self._provider

    async def complete(
        self,
        request: Any,
        *,
        card: ModelCard,
        credential: Any,
    ) -> ChatResponse:
        _ = (request, credential)
        return ChatResponse(
            id="cmpl-fake",
            created=1_700_000_000,
            model=card.code,
            choices=(
                Choice(
                    index=0,
                    message=ChatMessage(role=MessageRole.ASSISTANT, content=f"回答:{card.code}"),
                    finish_reason=FinishReason.STOP,
                ),
            ),
            usage=TokenUsage.of(120, 30),
        )


def build_test_container(telemetry: InMemoryTelemetrySink) -> AppContainer:
    """用确定性适配器替换真实厂商适配器，其余依赖沿用生产装配。"""
    base = build_container()
    base.telemetry = telemetry

    http = VendorHttpClient(SsrfPolicy(allowed_hosts=frozenset({"api.openai.com"})))
    registry = AdapterRegistry()
    for provider in PROVIDERS:
        registry.register(
            provider,
            lambda p=provider, h=http: EchoAdapter(p, h),
            capabilities=AdapterCapabilities(supports_stream=True, reports_usage=True),
        )

    credentials = InMemoryCredentialStore(platform_keys={p: f"sk-{p}" for p in PROVIDERS})
    invoker = ModelInvocationService(
        registry=registry,
        catalog=base.catalog,
        credentials=credentials,
        telemetry=telemetry,
        estimator=HeuristicTokenEstimator(),
        planner=FallbackPlanner(policy=RetryPolicy(max_attempts=1)),
    )
    gateway = ModelGatewayService(invoker)
    base.http = http
    base.registry = registry
    base.credentials = credentials
    base.invoker = invoker
    base.gateway = gateway
    base.playground = PlaygroundService(gateway)
    return base


@pytest.fixture
def telemetry() -> InMemoryTelemetrySink:
    return InMemoryTelemetrySink()


@pytest.fixture
def app(telemetry: InMemoryTelemetrySink) -> Iterator[FastAPI]:
    container = build_test_container(telemetry)
    application = create_app()
    # 覆盖单例依赖，让端点用测试容器
    application.dependency_overrides[get_container] = lambda: container
    application.state.container = container
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestModelsEndpoint:
    async def test_list_models_requires_tenant(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/v1/models")
        assert response.status_code == 400
        assert response.json()["code"] == "TENANT_CONTEXT_REQUIRED"

    async def test_list_models_shape(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/v1/models", headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["data"]
        first = body["data"][0]
        for field in ("code", "name", "provider", "capabilities"):
            assert field in first
        # 契约是 camelCase（序列化后不得出现 snake_case）
        assert "contextLength" in first
        assert "inputPer1k" in first["price"]
        assert "context_length" not in first

    async def test_trace_id_echoed(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/v1/models", headers=HEADERS)
        assert response.headers["X-Trace-Id"] == "trace-integration"


class TestErrorContract:
    """错误体必须符合 `schemas/common.yaml#/Error`：code/message/requestId 必填。"""

    async def test_error_body_shape(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/v1/models")
        assert response.status_code == 400
        body = response.json()
        for field in ("code", "message", "requestId"):
            assert field in body, f"错误体缺字段 {field}"

    async def test_credential_missing_maps_to_402(
        self, client: httpx.AsyncClient, app: FastAPI
    ) -> None:
        """租户可自行补 Key → 402（提示充值/配置），不是 5xx。"""
        container: AppContainer = app.state.container
        container.credentials.platform_keys.clear()
        response = await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 402
        assert response.json()["code"] == "CREDENTIAL_MISSING"


class TestChatEndpoint:
    async def test_completion_returns_contract_shape(
        self, client: httpx.AsyncClient, telemetry: InMemoryTelemetrySink
    ) -> None:
        response = await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "你好"}]},
        )
        assert response.status_code == 200
        body = response.json()
        for field in ("id", "created", "model", "choices", "usage"):
            assert field in body
        assert body["choices"][0]["message"]["content"] == "回答:gpt-4o"
        assert body["choices"][0]["finishReason"] == "stop"
        assert body["usage"]["credits"] > 0
        assert len(telemetry.events) == 1

    async def test_camel_case_alias_accepted(self, client: httpx.AsyncClient) -> None:
        """契约字段是 camelCase（maxTokens/appCode）——必须能收。"""
        response = await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
                "maxTokens": 128,
                "appCode": "app-1",
            },
        )
        assert response.status_code == 200

    async def test_unknown_model_returns_400(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={"model": "no-such-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "MODEL_NOT_FOUND"

    async def test_missing_tenant_rejected(self, client: httpx.AsyncClient) -> None:
        """铁律 6：没有租户上下文直接拒。"""
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 400

    async def test_empty_messages_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/completions", headers=HEADERS, json={"model": "gpt-4o", "messages": []}
        )
        assert response.status_code == 422

    async def test_invalid_role_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={"model": "gpt-4o", "messages": [{"role": "hacker", "content": "hi"}]},
        )
        assert response.status_code == 422

    async def test_temperature_out_of_range_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 5,
            },
        )
        assert response.status_code == 422

    async def test_retriable_error_maps_to_502(self, app: FastAPI) -> None:
        """厂商不可用（可重试）→ 502，让上游知道可以重试而不是改代码。"""
        container: AppContainer = app.state.container
        original = container.registry.resolve

        def _boom(provider: str) -> Any:
            adapter = original(provider)
            if isinstance(adapter, EchoAdapter):
                raise ProviderCallError("vendor 503")
            return adapter

        container.registry.resolve = _boom  # type: ignore[method-assign]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/v1/chat/completions",
                headers=HEADERS,
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert response.status_code == 502
        assert response.json()["code"] == "MODEL_CALL_FAILED"


class TestPlaygroundEndpoint:
    async def test_playground_completion(
        self, client: httpx.AsyncClient, telemetry: InMemoryTelemetrySink
    ) -> None:
        response = await client.post(
            "/_internal/playground/completions",
            headers=HEADERS,
            json={"model": "deepseek-chat", "prompt": "讲个笑话"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["content"] == "回答:deepseek-chat"
        assert body["usage"]["credits"] > 0
        # 关键：Playground 也必须计量（否则是免费刷模型的漏洞）
        assert len(telemetry.events) == 1
        assert telemetry.events[0].tenant_id == TENANT
        assert telemetry.events[0].model_code == "deepseek-chat"

    async def test_playground_requires_tenant(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/_internal/playground/completions",
            json={"model": "deepseek-chat", "prompt": "hi"},
        )
        assert response.status_code == 400

    async def test_playground_empty_prompt_422(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/_internal/playground/completions",
            headers=HEADERS,
            json={"model": "deepseek-chat", "prompt": ""},
        )
        assert response.status_code == 422

    async def test_playground_model_list(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/_internal/playground/models", headers=HEADERS)
        assert response.status_code == 200
        assert "deepseek-chat" in response.json()["data"]


class TestHealthEndpoints:
    async def test_healthz_no_auth(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_providers_reflects_registry(self, client: httpx.AsyncClient) -> None:
        """铁律 4 的可观测证据：注册了哪些厂商一目了然。"""
        response = await client.get("/healthz/providers", headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        providers = {p["provider"]: p for p in body["data"]}
        assert set(providers) == set(PROVIDERS)
        assert providers["anthropic"]["protocol"] == "native"
        assert providers["deepseek"]["protocol"] == "openai-compatible"

    async def test_providers_requires_tenant(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/healthz/providers")
        assert response.status_code == 400


class TestOpenApiGeneration:
    def test_app_exposes_openapi(self) -> None:
        """FastAPI 自动生成的 OpenAPI 必须可用（契约先生的地基）。"""
        spec = create_app().openapi()
        assert "/v1/chat/completions" in spec["paths"]
        assert "/v1/models" in spec["paths"]


class TestPlaygroundPage:
    """Playground 最小可用页面（M-08）——挂载在本服务内，不越界改 web-console。"""

    @pytest.mark.parametrize("path", ["/playground", "/playground/"])
    async def test_page_served(self, client: httpx.AsyncClient, path: str) -> None:
        response = await client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "模型试玩" in response.text

    async def test_page_calls_internal_api(self, client: httpx.AsyncClient) -> None:
        """页面必须调本服务的内部端点，而不是硬编码厂商地址。"""
        response = await client.get("/playground")
        assert "/_internal/playground/completions" in response.text
        assert "/_internal/playground/models" in response.text
