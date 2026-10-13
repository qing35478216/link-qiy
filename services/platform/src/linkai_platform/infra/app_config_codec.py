"""AppConfig（领域值对象）↔ JSON dict 编解码（infra 层；ORM JSON 列专用）。

纯映射，无 IO。契约字段 camelCase 与 JSON key 一致，直接透传。
"""

from __future__ import annotations

from typing import Any

from linkai_platform.domain.apps import (
    AdvancedConfig,
    AppConfig,
    BasicConfig,
    DataConfig,
    KnowledgeConfig,
    ModelPromptConfig,
    ModelPromptVariable,
    PluginsConfig,
    ShareConfig,
)

_SEGMENTS = ("basic", "share", "modelPrompt", "knowledge", "data", "plugins", "advanced")


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    """None 段落序列化为 {}（GET 响应保持七段形状稳定）。"""
    out: dict[str, Any] = {}
    if config.basic is not None:
        out["basic"] = _basic_to_dict(config.basic)
    if config.share is not None:
        out["share"] = _share_to_dict(config.share)
    if config.modelPrompt is not None:
        out["modelPrompt"] = _model_prompt_to_dict(config.modelPrompt)
    if config.knowledge is not None:
        out["knowledge"] = _knowledge_to_dict(config.knowledge)
    if config.data is not None:
        out["data"] = _data_to_dict(config.data)
    if config.plugins is not None:
        out["plugins"] = _plugins_to_dict(config.plugins)
    if config.advanced is not None:
        out["advanced"] = _advanced_to_dict(config.advanced)
    return out


def dict_to_config(data: dict[str, Any] | None) -> AppConfig:
    """JSON → AppConfig。缺段/空段 → None（清空语义）；多余键忽略。"""
    if not data:
        return AppConfig.empty()
    basic = _basic_from_dict(data.get("basic"))
    share = _share_from_dict(data.get("share"))
    model_prompt = _model_prompt_from_dict(data.get("modelPrompt"))
    knowledge = _knowledge_from_dict(data.get("knowledge"))
    d = _data_from_dict(data.get("data"))
    plugins = _plugins_from_dict(data.get("plugins"))
    advanced = _advanced_from_dict(data.get("advanced"))
    return AppConfig(
        basic=basic,
        share=share,
        modelPrompt=model_prompt,
        knowledge=knowledge,
        data=d,
        plugins=plugins,
        advanced=advanced,
    )


def _basic_to_dict(c: BasicConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.welcomeMessage is not None:
        out["welcomeMessage"] = c.welcomeMessage
    if c.guideQuestions is not None:
        out["guideQuestions"] = list(c.guideQuestions)
    if c.avatarUrl is not None:
        out["avatarUrl"] = c.avatarUrl
    return out


def _share_to_dict(c: ShareConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.shareEnabled is not None:
        out["shareEnabled"] = c.shareEnabled
    if c.sharePath is not None:
        out["sharePath"] = c.sharePath
    if c.showBranding is not None:
        out["showBranding"] = c.showBranding
    return out


def _model_prompt_to_dict(c: ModelPromptConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.modelCode is not None:
        out["modelCode"] = c.modelCode
    if c.systemPrompt is not None:
        out["systemPrompt"] = c.systemPrompt
    if c.temperature is not None:
        out["temperature"] = c.temperature
    if c.memoryRounds is not None:
        out["memoryRounds"] = c.memoryRounds
    if c.contextLength is not None:
        out["contextLength"] = c.contextLength
    if c.variables is not None:
        out["variables"] = [{"name": v.name, "value": v.value} for v in c.variables]
    return out


def _knowledge_to_dict(c: KnowledgeConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.datasetIds is not None:
        out["datasetIds"] = list(c.datasetIds)
    if c.similarityThreshold is not None:
        out["similarityThreshold"] = c.similarityThreshold
    if c.semanticTopK is not None:
        out["semanticTopK"] = c.semanticTopK
    if c.fulltextTopK is not None:
        out["fulltextTopK"] = c.fulltextTopK
    if c.missStrategy is not None:
        out["missStrategy"] = c.missStrategy
    if c.missMessage is not None:
        out["missMessage"] = c.missMessage
    if c.citationEnabled is not None:
        out["citationEnabled"] = c.citationEnabled
    if c.queryRewriteEnabled is not None:
        out["queryRewriteEnabled"] = c.queryRewriteEnabled
    if c.rerankEnabled is not None:
        out["rerankEnabled"] = c.rerankEnabled
    return out


def _data_to_dict(c: DataConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.dbDatasetId is not None:
        out["dbDatasetId"] = c.dbDatasetId
    if c.tableSyncCron is not None:
        out["tableSyncCron"] = c.tableSyncCron
    return out


def _plugins_to_dict(c: PluginsConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.pluginIds is not None:
        out["pluginIds"] = list(c.pluginIds)
    if c.execStrategy is not None:
        out["execStrategy"] = c.execStrategy
    if c.triggerKeywords is not None:
        out["triggerKeywords"] = list(c.triggerKeywords)
    return out


def _advanced_to_dict(c: AdvancedConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if c.humanTransferEnabled is not None:
        out["humanTransferEnabled"] = c.humanTransferEnabled
    if c.humanTransferKeyword is not None:
        out["humanTransferKeyword"] = c.humanTransferKeyword
    if c.humanizeEnabled is not None:
        out["humanizeEnabled"] = c.humanizeEnabled
    if c.rateLimitQpm is not None:
        out["rateLimitQpm"] = c.rateLimitQpm
    return out


def _basic_from_dict(d: dict[str, Any] | None) -> BasicConfig | None:
    if not d:
        return None
    return BasicConfig(
        welcomeMessage=d.get("welcomeMessage"),
        guideQuestions=d.get("guideQuestions"),
        avatarUrl=d.get("avatarUrl"),
    )


def _share_from_dict(d: dict[str, Any] | None) -> ShareConfig | None:
    if not d:
        return None
    return ShareConfig(
        shareEnabled=d.get("shareEnabled"),
        sharePath=d.get("sharePath"),
        showBranding=d.get("showBranding"),
    )


def _model_prompt_from_dict(d: dict[str, Any] | None) -> ModelPromptConfig | None:
    if not d:
        return None
    raw_vars = d.get("variables")
    variables = (
        [
            ModelPromptVariable(name=str(v.get("name", "")), value=str(v.get("value", "")))
            for v in raw_vars
        ]
        if isinstance(raw_vars, list)
        else None
    )
    return ModelPromptConfig(
        modelCode=d.get("modelCode"),
        systemPrompt=d.get("systemPrompt"),
        temperature=d.get("temperature"),
        memoryRounds=d.get("memoryRounds"),
        contextLength=d.get("contextLength"),
        variables=variables,
    )


def _knowledge_from_dict(d: dict[str, Any] | None) -> KnowledgeConfig | None:
    if not d:
        return None
    return KnowledgeConfig(
        datasetIds=d.get("datasetIds"),
        similarityThreshold=d.get("similarityThreshold"),
        semanticTopK=d.get("semanticTopK"),
        fulltextTopK=d.get("fulltextTopK"),
        missStrategy=d.get("missStrategy"),
        missMessage=d.get("missMessage"),
        citationEnabled=d.get("citationEnabled"),
        queryRewriteEnabled=d.get("queryRewriteEnabled"),
        rerankEnabled=d.get("rerankEnabled"),
    )


def _data_from_dict(d: dict[str, Any] | None) -> DataConfig | None:
    if not d:
        return None
    return DataConfig(dbDatasetId=d.get("dbDatasetId"), tableSyncCron=d.get("tableSyncCron"))


def _plugins_from_dict(d: dict[str, Any] | None) -> PluginsConfig | None:
    if not d:
        return None
    return PluginsConfig(
        pluginIds=d.get("pluginIds"),
        execStrategy=d.get("execStrategy"),
        triggerKeywords=d.get("triggerKeywords"),
    )


def _advanced_from_dict(d: dict[str, Any] | None) -> AdvancedConfig | None:
    if not d:
        return None
    return AdvancedConfig(
        humanTransferEnabled=d.get("humanTransferEnabled"),
        humanTransferKeyword=d.get("humanTransferKeyword"),
        humanizeEnabled=d.get("humanizeEnabled"),
        rateLimitQpm=d.get("rateLimitQpm"),
    )
