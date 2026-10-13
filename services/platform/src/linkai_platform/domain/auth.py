"""认证领域：令牌值对象、令牌服务抽象、外部登录 Provider 抽象。

TokenService 的实现在 infra（PyJWT）。domain 只定义语义：
- access token：短期，携带 sub/tid/typ=access
- refresh token：长期，携带 sub/tid/typ=refresh + jti（jti 入库支持吊销/轮换）
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from linkai_platform.domain.users import utcnow

TokenKind = Literal["access", "refresh"]


@dataclass(frozen=True)
class TokenPair:
    """令牌对（契约 common.yaml#/TokenPair）。"""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"  # noqa: S105 - 字面量 token type，非密钥


@dataclass(frozen=True)
class Principal:
    """已认证主体：用户 + 工作租户。"""

    user_id: str
    tenant_id: str


@dataclass(frozen=True)
class TokenClaims:
    """令牌声明（domain 视角，与具体 JWT 库解耦）。"""

    principal: Principal
    kind: TokenKind
    jti: str
    expires_at: datetime


class TokenService(Protocol):
    """令牌签发/校验抽象。实现只允许在 infra。"""

    def issue(self, principal: Principal, kind: TokenKind) -> tuple[str, TokenClaims]:
        """签发令牌，返回 (raw_token, claims)。jti 由实现生成。"""
        ...

    def verify(self, raw_token: str, expected_kind: TokenKind) -> TokenClaims:
        """校验签名/过期/类型；非法、过期或类型不符抛 InvalidToken。"""
        ...


class AuthError(Exception):
    """认证错误基类。"""

    code = "AUTH_ERROR"


class InvalidToken(AuthError):
    """签名非法 / 已过期 / 被篡改 / 类型不符。"""

    code = "INVALID_TOKEN"


class RefreshTokenRevoked(AuthError):
    """刷新令牌已吊销（登出或已轮换）。"""

    code = "REFRESH_TOKEN_REVOKED"


class InvalidSmsCode(AuthError):
    """验证码错误（含尝试次数耗尽）。"""

    code = "INVALID_SMS_CODE"


class AgreementNotAccepted(AuthError):
    """未勾选用户协议（契约：403 AGREEMENT_NOT_ACCEPTED）。"""

    code = "AGREEMENT_NOT_ACCEPTED"


# —— 外部 Provider 抽象（infra 提供 Mock / 真实实现；注册机制铁律 4 的适配器形态）——


@dataclass(frozen=True)
class QrTicket:
    """微信扫码票据。"""

    ticket: str
    qr_url: str
    expires_at: datetime


QrStatusName = Literal["pending", "scanned", "confirmed", "expired"]


@dataclass(frozen=True)
class QrStatus:
    """扫码状态；confirmed 时携带微信 openid 用于登录。"""

    status: QrStatusName
    openid: str | None = None


class WechatProvider(Protocol):
    """微信登录 Provider（开放平台扫码）。Phase 0 为 Mock 实现。"""

    def create_qrcode(self, scene: str, ttl_seconds: int) -> QrTicket:
        """生成扫码票据。"""
        ...

    def poll(self, ticket: str) -> QrStatus:
        """轮询扫码状态。"""
        ...


class SmsProvider(Protocol):
    """短信 Provider。domain 决定验证码内容，Provider 只负责投递。"""

    def send_code(self, phone: str, code: str, scene: str) -> None:
        """发送验证码；发送失败抛 SmsSendFailed。"""
        ...


class SmsSendFailed(AuthError):
    code = "SMS_SEND_FAILED"


def generate_sms_code(length: int = 6) -> str:
    """生成数字验证码（secrets，密码学安全随机）。"""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_refresh_jti() -> str:
    return secrets.token_urlsafe(32)


def new_ticket_id() -> str:
    return secrets.token_urlsafe(24)


def is_expired(expires_at: datetime, *, now: datetime | None = None) -> bool:
    moment = now if now is not None else utcnow()
    return moment >= expires_at
