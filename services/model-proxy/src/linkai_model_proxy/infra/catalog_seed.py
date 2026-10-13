"""模型目录种子数据——Phase 0 内置模型。

价格与上下文长度取厂商公开文档的量级值，**上线前须由人类核对最新价目**
（已列为工单遗留风险）。平台不"预设最佳模型"，这里只提供可调用的默认集合。

降级链示例设计意图：
- `deepseek-chat` → `glm-4-flash`：便宜且快的兜底；
- 国产厂商互为备选（国产→国产），避免跨境网络抖动；
- `qwen-plus` → `deepseek-chat` → `glm-4-flash`：三段式降级。
"""

from __future__ import annotations

from linkai_model_proxy.domain.model_card import (
    ModelCapability,
    ModelCard,
    ModelPrice,
)

#: 内置公共模型目录（tenant_id 无关，所有租户可见）
DEFAULT_MODEL_CATALOG: dict[str, ModelCard] = {
    # ---------- OpenAI ----------
    "gpt-4o": ModelCard(
        code="gpt-4o",
        name="GPT-4o",
        provider="openai",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.REASONING),
        context_length=128_000,
        price=ModelPrice(input_per_1k=0.018, output_per_1k=0.072),
        fallback_codes=("gpt-4o-mini", "deepseek-chat"),
    ),
    "gpt-4o-mini": ModelCard(
        code="gpt-4o-mini",
        name="GPT-4o mini",
        provider="openai",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION),
        context_length=128_000,
        price=ModelPrice(input_per_1k=0.001, output_per_1k=0.004),
        fallback_codes=("deepseek-chat",),
    ),
    # ---------- Anthropic ----------
    "claude-sonnet-4": ModelCard(
        code="claude-sonnet-4",
        name="Claude Sonnet 4",
        provider="anthropic",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.REASONING),
        context_length=200_000,
        price=ModelPrice(input_per_1k=0.022, output_per_1k=0.11),
        fallback_codes=("claude-haiku-4", "deepseek-chat"),
    ),
    "claude-haiku-4": ModelCard(
        code="claude-haiku-4",
        name="Claude Haiku 4",
        provider="anthropic",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION),
        context_length=200_000,
        price=ModelPrice(input_per_1k=0.007, output_per_1k=0.028),
        fallback_codes=("deepseek-chat",),
    ),
    # ---------- DeepSeek ----------
    "deepseek-chat": ModelCard(
        code="deepseek-chat",
        name="DeepSeek Chat",
        provider="deepseek",
        capabilities=(ModelCapability.CHAT, ModelCapability.REASONING),
        context_length=65_536,
        price=ModelPrice(input_per_1k=0.002, output_per_1k=0.008),
        fallback_codes=("glm-4-flash", "qwen-plus"),
    ),
    "deepseek-reasoner": ModelCard(
        code="deepseek-reasoner",
        name="DeepSeek Reasoner",
        provider="deepseek",
        capabilities=(ModelCapability.CHAT, ModelCapability.REASONING),
        context_length=65_536,
        price=ModelPrice(input_per_1k=0.004, output_per_1k=0.016),
        fallback_codes=("deepseek-chat",),
    ),
    # ---------- 通义千问 ----------
    "qwen-plus": ModelCard(
        code="qwen-plus",
        name="通义千问 Plus",
        provider="qwen",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION),
        context_length=131_072,
        price=ModelPrice(input_per_1k=0.0008, output_per_1k=0.002),
        fallback_codes=("deepseek-chat", "glm-4-flash"),
    ),
    "qwen-max": ModelCard(
        code="qwen-max",
        name="通义千问 Max",
        provider="qwen",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.REASONING),
        context_length=32_768,
        price=ModelPrice(input_per_1k=0.02, output_per_1k=0.06),
        fallback_codes=("qwen-plus", "deepseek-chat"),
    ),
    # ---------- 智谱 GLM ----------
    "glm-4-flash": ModelCard(
        code="glm-4-flash",
        name="GLM-4 Flash",
        provider="glm",
        capabilities=(ModelCapability.CHAT,),
        context_length=128_000,
        price=ModelPrice(input_per_1k=0.0001, output_per_1k=0.0001),
        fallback_codes=("qwen-plus",),
    ),
    "glm-4-plus": ModelCard(
        code="glm-4-plus",
        name="GLM-4 Plus",
        provider="glm",
        capabilities=(ModelCapability.CHAT, ModelCapability.VISION, ModelCapability.REASONING),
        context_length=128_000,
        price=ModelPrice(input_per_1k=0.005, output_per_1k=0.005),
        fallback_codes=("glm-4-flash", "deepseek-chat"),
    ),
}
