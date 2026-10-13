"""厂商适配器协议——**铁律 4 的核心扩展点**。

平台做框架、用户做创造：新接一家厂商 = 在 infra 层实现 `ProviderAdapter`
并调用 `AdapterRegistry.register()`，**内核（domain/services/api）零改动**。
本模块只定义 `Protocol`（结构化子类型），不 import 任何框架。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from linkai_model_proxy.domain.invocation import ChatRequest, ChatResponse, StreamDelta
from linkai_model_proxy.domain.model_card import ModelCard


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    """厂商凭证。

    `secret` 只在 infra 层流转，**禁止**进日志/事件/响应体；
    跨层传递一律用 `fingerprint()`（掩码）以便排障。
    """

    provider: str
    secret: str
    base_url: str | None = None
    extra_headers: Mapping[str, str] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """掩码指纹，用于日志与错误信息，绝不泄漏明文。"""
        if len(self.secret) <= 8:
            return "****"
        return f"{self.secret[:3]}****{self.secret[-4:]}"


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    """适配器能力声明——注册时自述，注册中心据此校验（避免注册了却调不通）。"""

    supports_stream: bool = True
    supports_tools: bool = False
    supports_vision: bool = False
    # 厂商原生是否返回 token 用量；False 时网关用估算器补齐（计量不能缺）
    reports_usage: bool = True


@runtime_checkable
class ModelAdapter(Protocol):
    """厂商适配器协议。

    生命周期由 `AdapterRegistry` 管理：注册的是**工厂**而非实例，
    这样注册表可以按租户/凭证维度构造实例，也便于测试时替换。
    """

    @property
    def provider(self) -> str:
        """厂商标识，与 `ModelCard.provider` 对应。"""
        ...

    @property
    def capabilities(self) -> AdapterCapabilities:
        """适配器能力声明。"""
        ...

    async def complete(
        self,
        request: ChatRequest,
        *,
        card: ModelCard,
        credential: ProviderCredential,
    ) -> ChatResponse:
        """非流式对话补全。失败须抛 `ProviderCallError` 子类以便降级链识别。"""
        ...

    def stream(
        self,
        request: ChatRequest,
        *,
        card: ModelCard,
        credential: ProviderCredential,
    ) -> AsyncIterator[StreamDelta]:
        """流式对话补全。

        返回异步迭代器，逐块产出 `StreamDelta`；**终局分片必须携带**
        `finish_reason` 与 `usage`（或由网关侧估算补齐），否则计量埋点会缺数。
        """
        ...


# ProviderAdapter 是给实现方看的文档化别名（协议本身即 ModelAdapter）
ProviderAdapter = ModelAdapter

# 适配器工厂：无参可调用，返回符合协议的实现
AdapterFactory = Callable[[], "ModelAdapter"]


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    """一条注册记录——描述"某厂商用哪个工厂造适配器"。"""

    provider: str
    factory: AdapterFactory
    capabilities: AdapterCapabilities
    # 是否允许用户自带 Key（自定义模型场景）。False 表示仅平台 Key 可用。
    allow_byok: bool = True

    def create(self) -> ModelAdapter:
        """实例化适配器。工厂签名必须是无参可调用。"""
        instance = self.factory()
        if not isinstance(instance, ModelAdapter):
            raise TypeError(f"工厂 {self.factory!r} 未产出符合 ModelAdapter 协议的实例")
        return instance
