"""Token 估算与平台配置解析用例。"""

from __future__ import annotations

from linkai_runtime.domain.app_profile import AppProfile
from linkai_runtime.domain.chat import ChatMessage, MessageRole
from linkai_runtime.domain.tokens import estimate_messages_tokens, estimate_tokens

DEMO_CONFIG: dict[str, object] = {
    "basic": {"welcomeMessage": "你好", "guideQuestions": ["q1", "q2"]},
    "modelPrompt": {
        "modelCode": "deepseek-chat",
        "systemPrompt": "你是助手",
        "temperature": 0.7,
        "memoryRounds": 5,
        "contextLength": 8192,
        "variables": [{"name": "role", "value": "客服"}],
    },
    "knowledge": {"datasetIds": ["ds-1", "ds-2"], "similarityThreshold": 0.6, "semanticTopK": 3},
    "plugins": {"pluginIds": ["p1"], "execStrategy": "knowledge_first"},
    "advanced": {"humanTransferEnabled": True, "rateLimitQpm": 60},
}


class TestTokenEstimator:
    def test_empty_is_zero(self) -> None:
        assert estimate_tokens("") == 0

    def test_cjk_one_token_per_char(self) -> None:
        assert estimate_tokens("你好世界") == 4

    def test_ascii_roughly_one_per_four_chars(self) -> None:
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcde") == 2

    def test_mixed(self) -> None:
        # 2 CJK + 4 ascii = 2 + 1 = 3
        assert estimate_tokens("你好abcd") == 3

    def test_messages_include_overhead(self) -> None:
        messages = (ChatMessage(role=MessageRole.USER, content="你好"),)
        assert estimate_messages_tokens(messages) == estimate_tokens("你好") + 4


class TestAppProfileParsing:
    def test_full_config_parsed(self) -> None:
        profile = AppProfile.from_platform_config(app_code="demo", config=DEMO_CONFIG)
        assert profile.app_code == "demo"
        assert profile.system_prompt == "你是助手"
        assert profile.model_code == "deepseek-chat"
        assert profile.temperature == 0.7
        assert profile.memory_rounds == 5
        assert profile.context_length == 8192
        assert profile.default_variables() == {"role": "客服"}
        assert profile.guide_questions == ("q1", "q2")
        assert profile.knowledge.dataset_ids == ("ds-1", "ds-2")
        assert profile.knowledge.similarity_threshold == 0.6
        assert profile.plugins.plugin_ids == ("p1",)
        assert profile.advanced.human_transfer_enabled is True
        assert profile.advanced.rate_limit_qpm == 60

    def test_empty_config_all_optional(self) -> None:
        profile = AppProfile.from_platform_config(app_code="demo", config={})
        assert profile.system_prompt is None
        assert profile.model_code is None
        assert profile.knowledge.dataset_ids == ()
        assert profile.default_variables() == {}

    def test_dirty_fields_tolerated(self) -> None:
        """用户可编辑数据：单字段脏不拖垮整体（防御式解析）。"""
        profile = AppProfile.from_platform_config(
            app_code="demo",
            config={
                "modelPrompt": {
                    "temperature": "hot",
                    "memoryRounds": "five",
                    "contextLength": None,
                },
                "knowledge": {"datasetIds": "not-a-list"},
            },
        )
        assert profile.temperature is None
        assert profile.memory_rounds is None
        assert profile.knowledge.dataset_ids == ()
