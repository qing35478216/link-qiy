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
