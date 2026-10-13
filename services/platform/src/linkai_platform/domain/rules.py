"""领域规则（纯函数，无 IO）：供 services 层编排时调用，保证核心规则可单测。

覆盖验收标准中的安全用例：协议勾选拒绝、刷新令牌轮换/吊销、过期判断。
"""

from __future__ import annotations

from linkai_platform.domain.auth import (
    AgreementNotAccepted,
    InvalidToken,
    RefreshTokenRevoked,
    TokenClaims,
    is_expired,
)
from linkai_platform.domain.repositories import RefreshTokenRecord
from linkai_platform.domain.users import utcnow


def require_agreement(accepted: bool) -> None:
    """登录必须勾选用户协议（契约：403 AGREEMENT_NOT_ACCEPTED）。"""
    if not accepted:
        raise AgreementNotAccepted("请先阅读并同意用户协议与隐私政策")


def assert_refresh_usable(record: RefreshTokenRecord | None, claims: TokenClaims) -> None:
    """刷新令牌可用性检查：记录存在、未吊销、未过期、归属一致。"""
    if record is None:
        raise InvalidToken("未知刷新令牌")
    if record.revoked:
        raise RefreshTokenRevoked("刷新令牌已吊销")
    if is_expired(record.expires_at):
        raise RefreshTokenRevoked("刷新令牌已过期")
    if record.user_id != claims.principal.user_id:
        raise InvalidToken("刷新令牌归属不一致")


def touch_agreement_acceptance(accepted: bool, accepted_at: object | None) -> bool:
    """返回本次登录是否需要回写协议接受时间（首次勾选才回写，幂等）。"""
    return accepted and accepted_at is None


def now_utc() -> object:
    """显式暴露给编排层的当前时间（便于测试替换）。"""
    return utcnow()
