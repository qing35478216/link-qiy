"""应用设定（AppProfile）——平台"配置七件套"在运行时的投影。

来源：services/platform 的 `AppConfig`（console-api.yaml Apps 段配置七件套：
basic/share/modelPrompt/knowledge/data/plugins/advanced）。runtime 不直连
platform 库表（铁律：跨服务禁止直接查库），经 `AppProfileProvider` 端口消费：
- 生产路径：PlatformHttpAppProfileProvider（HTTP，infra 层）
- Phase 0 联调路径：StaticAppProfileProvider（env 注入，infra 层）

本模块是**边界解析器**：把 platform 的 camelCase JSON 字典解析为强类型值对象。
纯 Python、可单测；字段全部可选（平台配置段落可缺省/已清空）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# ── platform AppConfigOut 的段落键（console-api.yaml v0.1.1）─────────
_KEY_BASIC = "basic"
_KEY_MODEL_PROMPT = "modelPrompt"
_KEY_KNOWLEDGE = "knowledge"
_KEY_PLUGINS = "plugins"
_KEY_ADVANCED = "advanced"


@dataclass(frozen=True, slots=True)
class PromptVariable:
    """提示词变量（应用设定的默认值；请求 variables 可覆盖）。"""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class KnowledgePolicy:
    """知识库策略（本期无知识库服务：仅透传配置，检索走端口占位）。"""

    dataset_ids: tuple[str, ...] = ()
    similarity_threshold: float | None = None
    semantic_top_k: int | None = None
    miss_strategy: str | None = None
    miss_message: str | None = None
    citation_enabled: bool | None = None


@dataclass(frozen=True, slots=True)
class PluginPolicy:
    """插件策略（执行策略：知识库优先/插件优先/并行汇总，Phase 1 落地）。"""

    plugin_ids: tuple[str, ...] = ()
    exec_strategy: str | None = None
    trigger_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdvancedPolicy:
    """高级设定。"""

    human_transfer_enabled: bool | None = None
    human_transfer_keyword: str | None = None
    humanize_enabled: bool | None = None
    rate_limit_qpm: int | None = None


@dataclass(frozen=True, slots=True)
class AppProfile:
    """运行时的应用设定投影（None 字段 = 平台未配置，装配时用领域回退常量）。"""

    app_code: str
    app_name: str = ""
    system_prompt: str | None = None
    model_code: str | None = None
    temperature: float | None = None
    memory_rounds: int | None = None
    context_length: int | None = None
    max_tokens: int | None = None
    variables: tuple[PromptVariable, ...] = ()
    welcome_message: str | None = None
    guide_questions: tuple[str, ...] = ()
    knowledge: KnowledgePolicy = field(default_factory=KnowledgePolicy)
    plugins: PluginPolicy = field(default_factory=PluginPolicy)
    advanced: AdvancedPolicy = field(default_factory=AdvancedPolicy)

    def default_variables(self) -> dict[str, str]:
        """应用设定的变量默认值（请求变量在此基础上覆盖）。"""
        return {v.name: v.value for v in self.variables}

    @classmethod
    def from_platform_config(
        cls,
        *,
        app_code: str,
        config: Mapping[str, object],
        app_name: str = "",
    ) -> AppProfile:
        """解析 platform `GET /apps/{id}/config` 的响应体（AppConfigOut）。

        防御式解析：平台字段全部可选，类型不符按缺省处理（不抛异常）——
        配置七件套是用户可编辑数据，运行时不能因单字段脏数据整体不可用。
        """
        basic = _mapping(config, _KEY_BASIC)
        model_prompt = _mapping(config, _KEY_MODEL_PROMPT)
        knowledge = _mapping(config, _KEY_KNOWLEDGE)
        plugins = _mapping(config, _KEY_PLUGINS)
        advanced = _mapping(config, _KEY_ADVANCED)
        return cls(
            app_code=app_code,
            app_name=app_name,
            system_prompt=_str(model_prompt, "systemPrompt"),
            model_code=_str(model_prompt, "modelCode"),
            temperature=_float(model_prompt, "temperature"),
            memory_rounds=_int(model_prompt, "memoryRounds"),
            context_length=_int(model_prompt, "contextLength"),
            variables=_variables(model_prompt),
            welcome_message=_str(basic, "welcomeMessage"),
            guide_questions=tuple(_str_list(basic, "guideQuestions")),
            knowledge=KnowledgePolicy(
                dataset_ids=tuple(_str_list(knowledge, "datasetIds")),
                similarity_threshold=_float(knowledge, "similarityThreshold"),
                semantic_top_k=_int(knowledge, "semanticTopK"),
                miss_strategy=_str(knowledge, "missStrategy"),
                miss_message=_str(knowledge, "missMessage"),
                citation_enabled=_bool(knowledge, "citationEnabled"),
            ),
            plugins=PluginPolicy(
                plugin_ids=tuple(_str_list(plugins, "pluginIds")),
                exec_strategy=_str(plugins, "execStrategy"),
                trigger_keywords=tuple(_str_list(plugins, "triggerKeywords")),
            ),
            advanced=AdvancedPolicy(
                human_transfer_enabled=_bool(advanced, "humanTransferEnabled"),
                human_transfer_keyword=_str(advanced, "humanTransferKeyword"),
                humanize_enabled=_bool(advanced, "humanizeEnabled"),
                rate_limit_qpm=_int(advanced, "rateLimitQpm"),
            ),
        )


# ── 防御式取值助手（纯函数）────────────────────────────────────


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    return value if isinstance(value, Mapping) else {}


def _str(source: Mapping[str, object], key: str) -> str | None:
    value = source.get(key)
    return value if isinstance(value, str) else None


def _int(source: Mapping[str, object], key: str) -> int | None:
    value = source.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(source: Mapping[str, object], key: str) -> float | None:
    value = source.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _bool(source: Mapping[str, object], key: str) -> bool | None:
    value = source.get(key)
    return value if isinstance(value, bool) else None


def _str_list(source: Mapping[str, object], key: str) -> list[str]:
    value = source.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _variables(source: Mapping[str, object]) -> tuple[PromptVariable, ...]:
    raw = source.get("variables")
    if not isinstance(raw, list):
        return ()
    out: list[PromptVariable] = []
    for item in raw:
        if isinstance(item, Mapping):
            name = item.get("name")
            value = item.get("value")
            if isinstance(name, str) and isinstance(value, str):
                out.append(PromptVariable(name=name, value=value))
    return tuple(out)
