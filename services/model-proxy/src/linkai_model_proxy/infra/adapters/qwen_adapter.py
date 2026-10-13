"""阿里通义千问（Qwen）适配器。

走阿里云百炼的 OpenAI 兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`
（国内）或 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`（国际）。
**不引入 `dashscope` SDK**：其依赖树含 requests/oss2 等，许可与体积均不划算，
且 OpenAI 兼容端点已覆盖文本对话（见 ADOPTED-TOOLS.md §2）。
"""

from __future__ import annotations

from typing import ClassVar

from linkai_model_proxy.domain.adapter import AdapterCapabilities
from linkai_model_proxy.infra.adapters.openai_compatible import OpenAICompatibleAdapter


class QwenAdapter(OpenAICompatibleAdapter):
    """阿里通义千问（qwen-plus / qwen-max / qwen-turbo 等）。"""

    PROVIDER: ClassVar[str] = "qwen"
    DEFAULT_BASE_URL: ClassVar[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    CHAT_PATH: ClassVar[str] = "/chat/completions"
    CAPABILITIES: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_stream=True, supports_tools=True, supports_vision=True, reports_usage=True
    )
    ALLOW_BYOK: ClassVar[bool] = True
