"""内置适配器注册——**新增厂商的唯一改动点**（铁律 4）。

加一家厂商的全部工作：
1. 在本目录下新建 `<vendor>_adapter.py`，继承 `OpenAICompatibleAdapter` 或直接实现 `ModelAdapter`；
2. 在 `BUILTIN_ADAPTERS` 里加一行；
3. （可选）在 `infra/catalog_seed.py` 加模型卡片。

**不需要**改 domain / services / api 任何一行代码。

想完全不碰本文件（插件化下发）？`register_builtins` 接受 `extra` 参数——
第三方包可以在自己进程里构造适配器后追加进来（"平台做框架、用户做创造"
在代码层的落点）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from linkai_model_proxy.domain.adapter import AdapterCapabilities, ModelAdapter
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.infra.adapters.anthropic_adapter import AnthropicAdapter
from linkai_model_proxy.infra.adapters.deepseek_adapter import DeepSeekAdapter
from linkai_model_proxy.infra.adapters.glm_adapter import ZhipuGlmAdapter
from linkai_model_proxy.infra.adapters.openai_adapter import OpenAIAdapter
from linkai_model_proxy.infra.adapters.openai_compatible import OpenAICompatibleAdapter
from linkai_model_proxy.infra.adapters.qwen_adapter import QwenAdapter
from linkai_model_proxy.infra.http_client import VendorHttpClient

#: 适配器实现类必须提供的类属性（供注册时读取能力声明）
AdapterClass = type[OpenAICompatibleAdapter] | type[AnthropicAdapter]


@dataclass(frozen=True, slots=True)
class BuiltinAdapter:
    """一条内置适配器声明。"""

    provider: str
    adapter_class: AdapterClass
    allow_byok: bool = True

    def factory(self, http: VendorHttpClient) -> Callable[[], ModelAdapter]:
        """生成注册表期望的无参工厂（闭包持有 http 客户端）。"""

        def build() -> ModelAdapter:
            instance = self.adapter_class(http)
            # 运行期校验：注册中心保证"注册了就能调"
            if not isinstance(instance, ModelAdapter):
                raise TypeError(f"{self.adapter_class.__name__} 未满足 ModelAdapter 协议")
            return instance

        build.__name__ = f"build_{self.adapter_class.__name__}"
        return build

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self.adapter_class.CAPABILITIES


#: 内置适配器表——**扩展点本体**：新增厂商在此追加一行即可
BUILTIN_ADAPTERS: tuple[BuiltinAdapter, ...] = (
    BuiltinAdapter("openai", OpenAIAdapter),
    BuiltinAdapter("anthropic", AnthropicAdapter),
    BuiltinAdapter("deepseek", DeepSeekAdapter),
    BuiltinAdapter("qwen", QwenAdapter),
    BuiltinAdapter("glm", ZhipuGlmAdapter),
)

#: 外部扩展工厂类型：接收 http 客户端，返回适配器
ExternalAdapterFactory = Callable[[VendorHttpClient], ModelAdapter]


def builtin_registry(http: VendorHttpClient) -> AdapterRegistry:
    """构造只含内置适配器的注册表。"""
    return register_builtins(AdapterRegistry(), http)


def register_builtins(
    registry: AdapterRegistry,
    http: VendorHttpClient,
    *,
    extra: Sequence[tuple[str, ExternalAdapterFactory]] = (),
) -> AdapterRegistry:
    """把内置（及可选外部）适配器注册进给定注册表。"""
    for entry in BUILTIN_ADAPTERS:
        registry.register(
            entry.provider,
            entry.factory(http),
            capabilities=entry.capabilities,
            allow_byok=entry.allow_byok,
        )
    for provider, factory in extra:
        registry.register(
            provider,
            _bind_external(factory, http),
            capabilities=_external_capabilities(factory),
            allow_byok=True,
        )
    return registry


def _bind_external(
    factory: ExternalAdapterFactory, http: VendorHttpClient
) -> Callable[[], ModelAdapter]:
    """把"接收 http 的外部工厂"绑定成"注册表期望的无参工厂"。"""

    def bound() -> ModelAdapter:
        return factory(http)

    bound.__name__ = "bound_external_adapter_factory"
    return bound


def _external_capabilities(factory: ExternalAdapterFactory) -> AdapterCapabilities:
    """外部适配器若暴露类级 `CAPABILITIES` 则读取，否则用默认值。"""
    caps = getattr(factory, "CAPABILITIES", None)
    return caps if isinstance(caps, AdapterCapabilities) else AdapterCapabilities()


def is_openai_compatible(provider: str) -> bool:
    """该厂商是否走 OpenAI 兼容协议（供健康检查与文档输出）。"""
    return provider not in ("anthropic",)


__all__ = [
    "BUILTIN_ADAPTERS",
    "AnthropicAdapter",
    "BuiltinAdapter",
    "DeepSeekAdapter",
    "OpenAIAdapter",
    "OpenAICompatibleAdapter",
    "QwenAdapter",
    "ZhipuGlmAdapter",
    "builtin_registry",
    "is_openai_compatible",
    "register_builtins",
]
