"""应用域：App 聚合根 + 配置七件套值对象（契约 console-api.yaml Apps 段）。

设计要点：
- 两类应用：lightweight（轻量）/ knowledge（知识库）
- 配置七件套：basic/share/modelPrompt/knowledge/data/plugins/advanced，
  全部字段可选（契约即如此）；PUT 为全量替换语义——未提供段落视为清空
- 配置版本：append-only 快照；PUT 保存即新版本；回滚同样产生新版本
  （内容复制旧版本），保证历史不可变
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from linkai_platform.domain.users import new_id, utcnow

APP_NAME_MAX = 64
APP_DESC_MAX = 512


class AppType(StrEnum):
    """应用类型枚举（契约 enum: lightweight/knowledge；all 仅列表过滤用）。"""

    LIGHTWEIGHT = "lightweight"
    KNOWLEDGE = "knowledge"
    ALL = "all"


VALID_APP_TYPES = frozenset({AppType.LIGHTWEIGHT.value, AppType.KNOWLEDGE.value})


class AppError(Exception):
    """应用域错误基类。"""

    code = "APP_ERROR"


class InvalidAppName(AppError):
    code = "INVALID_APP_NAME"


class InvalidAppType(AppError):
    code = "INVALID_APP_TYPE"


class AppNotFound(AppError):
    code = "APP_NOT_FOUND"


class AppVersionNotFound(AppError):
    code = "APP_VERSION_NOT_FOUND"


class AppLimitExceeded(AppError):
    """超出套餐应用数配额（docs/01 第十部分四档矩阵；Phase 0 服务端默认执行）。"""

    code = "APP_LIMIT_EXCEEDED"


# —— 配置七件套（值对象；字段全部可选，透传运行时，平台不预设最佳值）——


@dataclass(frozen=True)
class BasicConfig:
    welcomeMessage: str | None = None
    guideQuestions: list[str] | None = None
    avatarUrl: str | None = None


@dataclass(frozen=True)
class ShareConfig:
    shareEnabled: bool | None = None
    sharePath: str | None = None
    showBranding: bool | None = None


@dataclass(frozen=True)
class ModelPromptVariable:
    name: str
    value: str


@dataclass(frozen=True)
class ModelPromptConfig:
    modelCode: str | None = None
    systemPrompt: str | None = None
    temperature: float | None = None
    memoryRounds: int | None = None
    contextLength: int | None = None
    variables: list[ModelPromptVariable] | None = None


@dataclass(frozen=True)
class KnowledgeConfig:
    datasetIds: list[str] | None = None
    similarityThreshold: float | None = None
    semanticTopK: int | None = None
    fulltextTopK: int | None = None
    missStrategy: str | None = None
    missMessage: str | None = None
    citationEnabled: bool | None = None
    queryRewriteEnabled: bool | None = None
    rerankEnabled: bool | None = None


@dataclass(frozen=True)
class DataConfig:
    dbDatasetId: str | None = None
    tableSyncCron: str | None = None


@dataclass(frozen=True)
class PluginsConfig:
    pluginIds: list[str] | None = None
    execStrategy: str | None = None
    triggerKeywords: list[str] | None = None


@dataclass(frozen=True)
class AdvancedConfig:
    humanTransferEnabled: bool | None = None
    humanTransferKeyword: str | None = None
    humanizeEnabled: bool | None = None
    rateLimitQpm: int | None = None


@dataclass(frozen=True)
class AppConfig:
    """配置七件套容器。None 段落 = 已清空（PUT 全量替换语义）。"""

    basic: BasicConfig | None = None
    share: ShareConfig | None = None
    modelPrompt: ModelPromptConfig | None = None
    knowledge: KnowledgeConfig | None = None
    data: DataConfig | None = None
    plugins: PluginsConfig | None = None
    advanced: AdvancedConfig | None = None

    @classmethod
    def empty(cls) -> AppConfig:
        return cls()


@dataclass
class App:
    """应用聚合根。"""

    id: str
    tenant_id: str
    name: str
    type: str
    description: str | None = None
    icon_url: str | None = None
    published: bool = False
    current_version: int = 0
    current_config: AppConfig = field(default_factory=AppConfig.empty)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        name: str,
        type: str,
        description: str | None = None,
        icon_url: str | None = None,
    ) -> App:
        validate_app_name(name)
        if type not in VALID_APP_TYPES:
            raise InvalidAppType(f"应用类型必须是 lightweight/knowledge: {type!r}")
        if description is not None and len(description) > APP_DESC_MAX:
            raise InvalidAppName(f"简介长度超过 {APP_DESC_MAX}")
        now = utcnow()
        return cls(
            id=new_id(),
            tenant_id=tenant_id,
            name=name,
            type=type,
            description=description,
            icon_url=icon_url,
            created_at=now,
            updated_at=now,
        )

    def update_basic(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        icon_url: str | None = None,
    ) -> None:
        """更新基础信息（PATCH /apps/{id}，部分字段语义）。"""
        if name is not None:
            validate_app_name(name)
            self.name = name
        if description is not None:
            if len(description) > APP_DESC_MAX:
                raise InvalidAppName(f"简介长度超过 {APP_DESC_MAX}")
            self.description = description
        if icon_url is not None:
            self.icon_url = icon_url
        self.updated_at = utcnow()

    def replace_config(self, config: AppConfig) -> int:
        """全量替换配置并升版本；返回新版本号（PUT 语义）。"""
        self.current_config = config
        self.current_version += 1
        self.updated_at = utcnow()
        return self.current_version

    def snapshot(self) -> int:
        """手动快照：以当前配置内容记一个检查点版本，返回新版本号。"""
        self.current_version += 1
        self.updated_at = utcnow()
        return self.current_version

    def rollback_to(self, config: AppConfig) -> int:
        """回滚：把指定版本内容设为当前配置并产生新版本（append-only）。"""
        self.current_config = config
        self.current_version += 1
        self.updated_at = utcnow()
        return self.current_version

    def publish(self) -> None:
        self.published = True
        self.updated_at = utcnow()

    def unpublish(self) -> None:
        self.published = False
        self.updated_at = utcnow()


def validate_app_name(name: str) -> None:
    if not (1 <= len(name) <= APP_NAME_MAX):
        raise InvalidAppName(f"应用名长度须为 1-{APP_NAME_MAX} 字符")


@dataclass(frozen=True)
class AppVersion:
    """配置版本快照（append-only）。"""

    app_id: str
    tenant_id: str
    version: int
    config: AppConfig
    source: str  # save | snapshot | rollback
    created_at: datetime
