"""Pydantic 请求/响应模型（契约 packages/contracts/openapi/console-api.yaml v0.1.0 的对应物）。

字段命名对齐契约（camelCase）；Pydantic 只允许出现在 api 层。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateWechatQrcodeRequest(BaseModel):
    scene: str = Field(default="login", pattern="^(login|bind)$")


class CreateWechatQrcodeResponse(BaseModel):
    ticket: str
    qrUrl: str
    expiresAt: datetime


class WechatQrcodeStatusResponse(BaseModel):
    status: str = Field(pattern="^(pending|scanned|confirmed|expired)$")
    tokens: TokenPairResponse | None = None


class SendSmsCodeRequest(BaseModel):
    phone: str
    scene: str = Field(default="login", pattern="^(login|bind)$")


class PhoneLoginRequest(BaseModel):
    phone: str
    smsCode: str = Field(min_length=4, max_length=8)
    agreementAccepted: bool


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class TokenPairResponse(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int
    tokenType: str = "Bearer"


class UserProfileResponse(BaseModel):
    """UserProfile（契约 components.schemas.UserProfile）。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    nickname: str
    avatarUrl: str | None = None
    phone: str | None = None
    plan: str = "basic"
    agreementAcceptedAt: datetime | None = None


class UserProfileUpdateRequest(BaseModel):
    """PATCH /me 请求体。契约 v0.1.1：UserProfile 的 id/plan/agreementAcceptedAt 为
    readOnly（防越权改套餐/协议时间），extra="forbid" 保证携带即 422。"""

    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(default=None, max_length=64)
    avatarUrl: str | None = None
    phone: str | None = None


# —— Apps（契约 console-api.yaml Apps 段）——


class AppCreateRequest(BaseModel):
    """POST /apps 请求体。App 契约中 readOnly 字段（id/published/currentVersion/
    createdAt/updatedAt）以 extra="forbid" 拒绝携带。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    type: str = Field(pattern="^(lightweight|knowledge)$")
    description: str | None = Field(default=None, max_length=512)
    iconUrl: str | None = None


class AppUpdateRequest(BaseModel):
    """PATCH /apps/{appId} 请求体（基础信息部分更新）。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    iconUrl: str | None = None


class AppResponse(BaseModel):
    """App（契约 components.schemas.App）。"""

    id: str
    name: str
    description: str | None = None
    type: str
    iconUrl: str | None = None
    published: bool = False
    currentVersion: int = 0
    createdAt: datetime
    updatedAt: datetime


class BasicConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    welcomeMessage: str | None = None
    guideQuestions: list[str] | None = Field(default=None, max_length=5)
    avatarUrl: str | None = None


class ShareConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shareEnabled: bool | None = None
    sharePath: str | None = None
    showBranding: bool | None = None


class ModelPromptVariableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str


class ModelPromptConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modelCode: str | None = None
    systemPrompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    memoryRounds: int | None = Field(default=None, ge=0, le=50)
    contextLength: int | None = None
    variables: list[ModelPromptVariableIn] | None = None


class KnowledgeConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasetIds: list[str] | None = None
    similarityThreshold: float | None = Field(default=None, ge=0, le=1)
    semanticTopK: int | None = None
    fulltextTopK: int | None = None
    missStrategy: str | None = Field(default=None, pattern="^(free|fixedMessage|humanTransfer)$")
    missMessage: str | None = None
    citationEnabled: bool | None = None
    queryRewriteEnabled: bool | None = None
    rerankEnabled: bool | None = None


class DataConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dbDatasetId: str | None = None
    tableSyncCron: str | None = None


class PluginsConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pluginIds: list[str] | None = None
    execStrategy: str | None = Field(
        default=None, pattern="^(knowledgeFirst|pluginFirst|parallel)$"
    )
    triggerKeywords: list[str] | None = None


class AdvancedConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    humanTransferEnabled: bool | None = None
    humanTransferKeyword: str | None = None
    humanizeEnabled: bool | None = None
    rateLimitQpm: int | None = None


class AppConfigIn(BaseModel):
    """PUT /apps/{appId}/config 请求体：七件套全量替换，缺段即清空。"""

    model_config = ConfigDict(extra="forbid")

    basic: BasicConfigIn | None = None
    share: ShareConfigIn | None = None
    modelPrompt: ModelPromptConfigIn | None = None
    knowledge: KnowledgeConfigIn | None = None
    data: DataConfigIn | None = None
    plugins: PluginsConfigIn | None = None
    advanced: AdvancedConfigIn | None = None


class AppConfigOut(BaseModel):
    """七件套读取响应：清空段落返回 {}（保持七段形状稳定）。"""

    basic: dict[str, object] = Field(default_factory=dict)
    share: dict[str, object] = Field(default_factory=dict)
    modelPrompt: dict[str, object] = Field(default_factory=dict)
    knowledge: dict[str, object] = Field(default_factory=dict)
    data: dict[str, object] = Field(default_factory=dict)
    plugins: dict[str, object] = Field(default_factory=dict)
    advanced: dict[str, object] = Field(default_factory=dict)


class VersionResponse(BaseModel):
    version: int


class AppVersionItem(BaseModel):
    version: int
    source: str
    createdAt: datetime


class PageResponse(BaseModel):
    items: list[object]
    nextCursor: str | None = None


class QuotaUsageResponse(BaseModel):
    messagesUsed: int = 0
    messagesLimit: int = 0
    tokensUsed: int = 0
    tokensLimit: int = 0


class QuotaSummaryResponse(BaseModel):
    plan: str
    planBadge: str
    walletBalance: int = 0
    upgradeUrl: str | None = None
    usage: QuotaUsageResponse = Field(default_factory=QuotaUsageResponse)
