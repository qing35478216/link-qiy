"""适配器注册中心——**铁律 4 的落地点**。

契约（不变的部分）：
- 注册表以 `provider` 字符串为键，同一 provider 重复注册**拒绝**（防误覆盖静默生效）；
- 内核只认`AdapterRegistration`，不认识任何具体厂商；
- `resolve()` 在未注册时抛 `AdapterNotRegisteredError`，由 api 层翻译成错误响应。

可变部分（这就是"加厂商不改内核"的全部含义）：
- 在 infra/adapters/ 下新增一个实现 `ModelAdapter` 的类；
- 在 `builtin_registry()` 里加一行 `registry.register(...)`；
除此以外**不需要**改 domain / services / api 任何一行代码。
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from linkai_model_proxy.domain.adapter import (
    AdapterCapabilities,
    AdapterFactory,
    AdapterRegistration,
    ModelAdapter,
)
from linkai_model_proxy.domain.errors import AdapterNotRegisteredError, DomainError


class AdapterRegistry:
    """厂商适配器注册表。

    线程安全由调用方保证（FastAPI 同步注册一次、之后只读）。
    """

    def __init__(self) -> None:
        self._registrations: dict[str, AdapterRegistration] = {}

    def register(
        self,
        provider: str,
        factory: AdapterFactory,
        *,
        capabilities: AdapterCapabilities | None = None,
        allow_byok: bool = True,
    ) -> AdapterRegistration:
        """注册一个厂商适配器工厂。

        这是**唯一**的扩展入口——新增厂商不需要改动任何其他文件。
        重复注册同一 provider 会抛错，避免线上"后注册静默覆盖前者"的隐性行为。
        """
        if not provider:
            raise DomainError("provider 不能为空")
        if provider in self._registrations:
            raise DomainError(f"厂商 {provider!r} 已注册，不允许覆盖（如需替换请显式 unregister）")

        registration = AdapterRegistration(
            provider=provider,
            factory=factory,
            capabilities=capabilities or AdapterCapabilities(),
            allow_byok=allow_byok,
        )
        self._registrations[provider] = registration
        return registration

    def unregister(self, provider: str) -> None:
        """移除注册（测试与热插拔用）。"""
        self._registrations.pop(provider, None)

    def resolve(self, provider: str) -> ModelAdapter:
        """取出适配器实例。未注册抛 `AdapterNotRegisteredError`。"""
        registration = self._registrations.get(provider)
        if registration is None:
            known = ", ".join(sorted(self._registrations)) or "(空)"
            raise AdapterNotRegisteredError(f"厂商 {provider!r} 未注册适配器；已注册：{known}")
        return registration.create()

    def get_registration(self, provider: str) -> AdapterRegistration | None:
        """取注册记录（不实例化）——用于查询 `allow_byok` 等元信息。"""
        return self._registrations.get(provider)

    def is_registered(self, provider: str) -> bool:
        return provider in self._registrations

    def providers(self) -> tuple[str, ...]:
        """已注册厂商列表（排序，保证输出稳定）。"""
        return tuple(sorted(self._registrations))

    def snapshot(self) -> Mapping[str, AdapterRegistration]:
        """只读快照，供 `/v1/models` 与健康检查输出。"""
        return MappingProxyType(dict(self._registrations))

    def __len__(self) -> int:
        return len(self._registrations)

    def __contains__(self, provider: object) -> bool:
        return isinstance(provider, str) and provider in self._registrations
