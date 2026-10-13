"""智谱 GLM 适配器。

走智谱开放平台 OpenAI 兼容端点 `https://open.bigmodel.cn/api/paas/v4`。
**不引入 `zhipuai` SDK**：官方 `MetaGLM/zhipuai-sdk-python-v4` 为 MIT 但star 数
（198）远低于社区主流、最后提交 2025-10，OpenAI 兼容端点已覆盖对话场景
（见 ADOPTED-TOOLS.md §2 的四项核查结论）。
"""

from __future__ import annotations

from typing import ClassVar

from linkai_model_proxy.domain.adapter import AdapterCapabilities
from linkai_model_proxy.infra.adapters.openai_compatible import OpenAICompatibleAdapter


class ZhipuGlmAdapter(OpenAICompatibleAdapter):
    """智谱 GLM（glm-4 / glm-4-flash / glm-4-plus 等）。"""

    PROVIDER: ClassVar[str] = "glm"
    DEFAULT_BASE_URL: ClassVar[str] = "https://open.bigmodel.cn/api/paas/v4"
    CHAT_PATH: ClassVar[str] = "/chat/completions"
    CAPABILITIES: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_stream=True, supports_tools=True, reports_usage=True
    )
    ALLOW_BYOK: ClassVar[bool] = True
