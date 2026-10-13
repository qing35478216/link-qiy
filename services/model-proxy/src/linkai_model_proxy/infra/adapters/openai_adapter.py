"""OpenAI 官方适配器。

注意：`openai` 官方 Python SDK（Apache-2.0）本可直连，但本工单统一走
OpenAI 兼容 HTTP 以避免每个厂商一个 SDK 的依赖面（理由见 ADOPTED-TOOLS.md §2）。
需要 SDK 特性（如 Assistants API、内建重试策略）时再单独立项引入。
"""

from __future__ import annotations

from typing import ClassVar

from linkai_model_proxy.domain.adapter import AdapterCapabilities
from linkai_model_proxy.infra.adapters.openai_compatible import OpenAICompatibleAdapter


class OpenAIAdapter(OpenAICompatibleAdapter):
    """OpenAI（ChatGPT / GPT 系列）。"""

    PROVIDER: ClassVar[str] = "openai"
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.openai.com/v1"
    CHAT_PATH: ClassVar[str] = "/chat/completions"
    CAPABILITIES: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_stream=True, supports_tools=True, supports_vision=True, reports_usage=True
    )
    ALLOW_BYOK: ClassVar[bool] = True
