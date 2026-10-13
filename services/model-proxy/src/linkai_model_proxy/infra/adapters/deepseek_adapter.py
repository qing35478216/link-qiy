"""DeepSeek 适配器。

DeepSeek 提供 OpenAI 兼容端点（`https://api.deepseek.com`），无需专有 SDK。
`deepseek-reasoner` 模型的 `temperature` 参数不受支持（官方限制），
调用时需剔除——这正是"适配器承载厂商特例"的典型场景。
"""

from __future__ import annotations

from typing import ClassVar

from linkai_model_proxy.domain.adapter import AdapterCapabilities
from linkai_model_proxy.domain.invocation import ChatRequest
from linkai_model_proxy.domain.model_card import ModelCard
from linkai_model_proxy.infra.adapters.openai_compatible import OpenAICompatibleAdapter
from linkai_model_proxy.infra.http_client import JsonDict


class DeepSeekAdapter(OpenAICompatibleAdapter):
    """DeepSeek（deepseek-chat / deepseek-reasoner）。"""

    PROVIDER: ClassVar[str] = "deepseek"
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.deepseek.com/v1"
    CHAT_PATH: ClassVar[str] = "/chat/completions"
    CAPABILITIES: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_stream=True, supports_tools=True, reports_usage=True
    )
    ALLOW_BYOK: ClassVar[bool] = True

    #: 推理模型不接受采样参数
    REASONER_CODES: ClassVar[frozenset[str]] = frozenset({"deepseek-reasoner"})

    def extra_payload(self, payload: JsonDict, request: ChatRequest, card: ModelCard) -> None:
        if card.code in self.REASONER_CODES:
            payload.pop("temperature", None)
            payload.pop("max_tokens", None)
