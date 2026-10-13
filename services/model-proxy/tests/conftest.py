"""测试夹具——复用领域夹具 + 内存端口实现。

设计：夹具全部在 `tests/conftest.py`，用例文件只关心被测行为。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from linkai_model_proxy.domain.adapter import (
    AdapterCapabilities,
    ProviderCredential,
)
from linkai_model_proxy.domain.errors import ProviderCallError
from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Choice,
    FinishReason,
    MessageRole,
    StreamDelta,
    TokenUsage,
)
from linkai_model_proxy.domain.model_card import (
    ModelCapability,
    ModelCard,
    ModelPrice,
    ProviderId,
)
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.infra.adapters import builtin_registry
from linkai_model_proxy.infra.catalog_seed import DEFAULT_MODEL_CATALOG
from linkai_model_proxy.infra.http_client import VendorHttpClient
from linkai_model_proxy.infra.memory import (
    HeuristicTokenEstimator,
    InMemoryCredentialStore,
    InMemoryModelCatalog,
    InMemoryTelemetrySink,
)
from linkai_model_proxy.infra.ssrf import SsrfPolicy

TENANT = "tenant-test-001"
OTHER_TENANT = "tenant-test-002"

#: 测试专用白名单：这些 host 不做 DNS 解析（避免用例依赖网络）
TEST_ALLOWED_HOSTS = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "api.deepseek.com",
        "dashscope.aliyuncs.com",
        "open.bigmodel.cn",
        "mock-vendor.test",
    }
)


@pytest.fixture
def ssrf_policy() -> SsrfPolicy:
    """测试策略：允许 https、白名单校验开启、零退避。"""
    return SsrfPolicy(allowed_hosts=TEST_ALLOWED_HOSTS, allow_http=False)


@pytest.fixture
async def vendor_http(ssrf_policy: SsrfPolicy) -> AsyncIterator[VendorHttpClient]:
    client = VendorHttpClient(ssrf_policy)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def registry(vendor_http: VendorHttpClient) -> AdapterRegistry:
    return builtin_registry(vendor_http)


@pytest.fixture
def catalog() -> InMemoryModelCatalog:
    return InMemoryModelCatalog(public_models=DEFAULT_MODEL_CATALOG)


@pytest.fixture
def telemetry() -> InMemoryTelemetrySink:
    return InMemoryTelemetrySink()


@pytest.fixture
def credentials() -> InMemoryCredentialStore:
    return InMemoryCredentialStore(
        platform_keys={provider.value: f"sk-test-{provider.value}-key" for provider in ProviderId}
    )


@pytest.fixture
def estimator() -> HeuristicTokenEstimator:
    return HeuristicTokenEstimator()


# ---------- 构造器助手 ----------


def make_card(
    code: str = "mock-chat",
    provider: str = "mock-vendor",
    *,
    fallback_codes: tuple[str, ...] = (),
    price: ModelPrice | None = None,
    enabled: bool = True,
) -> ModelCard:
    return ModelCard(
        code=code,
        name=code.upper(),
        provider=provider,
        capabilities=(ModelCapability.CHAT,),
        context_length=8_192,
        price=price or ModelPrice(input_per_1k=1.0, output_per_1k=2.0),
        enabled=enabled,
        fallback_codes=fallback_codes,
    )


def make_request(
    model: str = "mock-chat", *, stream: bool = False, content: str = "你好"
) -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=(ChatMessage(role=MessageRole.USER, content=content),),
        stream=stream,
    )


def make_response(
    text: str = "mock-answer",
    *,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> ChatResponse:
    return ChatResponse(
        id="cmpl-mock",
        created=1_700_000_000,
        model="mock-chat",
        choices=(
            Choice(
                index=0,
                message=ChatMessage(role=MessageRole.ASSISTANT, content=text),
                finish_reason=FinishReason.STOP,
            ),
        ),
        usage=TokenUsage.of(prompt_tokens, completion_tokens),
    )


@dataclass
class ScriptedAdapter:
    """可编排的假适配器——用于降级链与错误路径用例。"""

    provider: str
    response: ChatResponse | None = None
    error: Exception | None = None
    chunks: tuple[str, ...] = ()
    chunk_usage: TokenUsage | None = None
    capabilities: AdapterCapabilities = field(
        default_factory=lambda: AdapterCapabilities(supports_stream=True, reports_usage=True)
    )
    calls: list[str] = field(default_factory=list)

    @property
    def capabilities_(self) -> AdapterCapabilities:  # pragma: no cover - 兼容别名
        return self.capabilities

    async def complete(
        self,
        request: ChatRequest,
        *,
        card: ModelCard,
        credential: ProviderCredential,
    ) -> ChatResponse:
        self.calls.append(card.code)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise ProviderCallError("ScriptedAdapter 未配置响应", retriable=False)
        return self.response

    async def stream(
        self,
        request: ChatRequest,
        *,
        card: ModelCard,
        credential: ProviderCredential,
    ) -> AsyncIterator[StreamDelta]:
        self.calls.append(card.code)
        if self.error is not None:
            raise self.error
        for index, chunk in enumerate(self.chunks):
            terminal = index == len(self.chunks) - 1
            yield StreamDelta(
                delta=chunk,
                seq=index,
                finish_reason=FinishReason.STOP if terminal else None,
                usage=self.chunk_usage if terminal else None,
            )


class ScriptedAdapterFactory:
    """把 `ScriptedAdapter` 包成注册表需要的无参工厂。"""

    def __init__(self, adapter: ScriptedAdapter) -> None:
        self._adapter = adapter

    def __call__(self) -> Any:
        return self._adapter


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """兜底护栏：漏mock 的出网请求会让用例失败（而非真的打到厂商）。

    打在 **socket 层**——比 respx 的 mock（httpx `_transport_for_url` /
    httpcore `handle_async_request`）更低，因此用例内的 `with respx.mock:`
    依然生效，而真正漏网时会立刻炸出来。
    """
    import socket

    def _blocked(self: socket.socket, *args: object, **kwargs: object) -> None:
        raise AssertionError(f"测试中禁止真实出网（目标 {args[:2]}）——请用 respx mock 回放厂商响应")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
