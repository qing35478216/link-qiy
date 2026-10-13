"""模型卡片——描述一个可被调用的模型及其厂商归属、价格与能力。

领域对象（不可变），供`/v1/models` 契约端点与降级链/计量共用。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class ProviderId(StrEnum):
    """已注册的厂商标识。

    注意：此处枚举只是**内置适配器的快捷别名**，不是厂商白名单。
    新增厂商时无需改内核——在 infra 层实现 `ProviderAdapter` 并调用
    `AdapterRegistry.register()` 即可，自定义厂商可用其自有 `code` 字符串
    （见 `ModelCard.provider` 的类型：它接受任意 `str`）。
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    GLM = "glm"


class ModelCapability(StrEnum):
    """七类能力抽象（对应 docs/03 角色定义）。取值与契约 `Model.capabilities` 一致。"""

    CHAT = "chat"
    REASONING = "reasoning"
    VISION = "vision"
    IMAGE_GEN = "imageGen"
    VIDEO_GEN = "videoGen"
    TTS = "tts"
    ASR = "asr"
    DECISION = "decision"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """模型价格。credits 为整数积分，由 `CreditCalculator` 按token 折算。

    契约 `Model.price`：inputPer1k / outputPer1k / creditPerCall。
    """

    input_per_1k: float = 0.0
    output_per_1k: float = 0.0
    credit_per_call: int = 0


@dataclass(frozen=True, slots=True)
class ModelCard:
    """一个模型的元数据。

    `fallback_codes` 是**降级链**声明：主模型失败时按顺序尝试这些模型编码。
    平台不预设"最佳降级策略"——由模型目录配置驱动（角色定义要求）。
    """

    code: str
    name: str
    provider: str
    capabilities: tuple[ModelCapability, ...]
    context_length: int = 0
    price: ModelPrice = field(default_factory=ModelPrice)
    enabled: bool = True
    fallback_codes: tuple[str, ...] = ()

    def supports(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True, slots=True)
class ModelRef:
    """解析后的模型引用——模型卡片 + 租户维度的路由决策输入。"""

    card: ModelCard
    tenant_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id 不能为空——多租户隔离强约束（铁律 6）")


@dataclass(frozen=True, slots=True)
class ModelCatalogSnapshot:
    """模型目录的一次只读快照。

    用 `MappingProxyType` 冻结，防止 infra 层误改领域数据。
    """

    models: Mapping[str, ModelCard]

    @classmethod
    def of(cls, models: Mapping[str, ModelCard]) -> ModelCatalogSnapshot:
        return cls(models=MappingProxyType(dict(models)))

    def get(self, code: str) -> ModelCard | None:
        return self.models.get(code)

    def enabled_models(self) -> tuple[ModelCard, ...]:
        return tuple(m for m in self.models.values() if m.enabled)
