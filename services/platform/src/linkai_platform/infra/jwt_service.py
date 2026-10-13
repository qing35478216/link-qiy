"""TokenService 的 PyJWT 实现（选型见 ADOPTED-TOOLS.md）。

声明设计：
- sub=user_id, tid=tenant_id（多租户穿透，docs/03 3.4）
- typ=access|refresh（防令牌类型混淆），jti 刷新令牌入库支持吊销/轮换
- iss=linkai-platform, exp/iat 标准声明
仅使用 HS256；验证时显式 algorithms 白名单，禁 alg=none。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidAlgorithmError, InvalidTokenError

from linkai_platform.domain.auth import (
    InvalidToken,
    Principal,
    TokenClaims,
    TokenKind,
    generate_refresh_jti,
)
from linkai_platform.domain.users import utcnow

ISSUER = "linkai-platform"
ALGORITHM = "HS256"


class PyJwtTokenService:
    def __init__(
        self,
        *,
        secret: str,
        access_ttl_seconds: int = 3600,
        refresh_ttl_seconds: int = 30 * 24 * 3600,
        _now: Callable[[], datetime] | None = None,  # 测试注入时钟；生产为 None
        leeway_seconds: int = 0,  # 时钟偏移容忍；测试用负值模拟过期
    ) -> None:
        self._secret = secret
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds
        self._now = _now or utcnow
        self._leeway = leeway_seconds

    def issue(self, principal: Principal, kind: TokenKind) -> tuple[str, TokenClaims]:
        now = self._now()
        ttl = self._access_ttl if kind == "access" else self._refresh_ttl
        jti = generate_refresh_jti()  # access/refresh 都带 jti，便于审计与吊销扩展
        payload = {
            "iss": ISSUER,
            "sub": principal.user_id,
            "tid": principal.tenant_id,
            "typ": kind,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        }
        raw = jwt.encode(payload, self._secret, algorithm=ALGORITHM)
        return raw, TokenClaims(
            principal=principal, kind=kind, jti=jti, expires_at=now + timedelta(seconds=ttl)
        )

    def verify(self, raw_token: str, expected_kind: TokenKind) -> TokenClaims:
        try:
            payload = jwt.decode(
                raw_token,
                self._secret,
                algorithms=[ALGORITHM],  # 显式白名单，禁 alg=none
                issuer=ISSUER,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "sub", "tid", "typ", "jti"]},
            )
        except (InvalidTokenError, InvalidAlgorithmError) as exc:
            raise InvalidToken(f"令牌校验失败: {exc}") from exc
        if payload["typ"] != expected_kind:
            raise InvalidToken(f"令牌类型不符: 期望 {expected_kind}")
        return TokenClaims(
            principal=Principal(user_id=payload["sub"], tenant_id=payload["tid"]),
            kind=expected_kind,
            jti=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
