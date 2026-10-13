"""JWT 校验（与 platform 共享密钥；billing 只校验不签发）。

platform 为账户域事实源（登录/签发在此）；billing 控制台面 API 复用
同一套 HS256 访问令牌做身份判定（租户隔离铁律 6 的服务侧 enforcement）。
显式 algorithms=["HS256"] 白名单防 alg=none（platform 同款适配）。
"""

from __future__ import annotations

import jwt

from linkai_billing.domain.auth import Principal
from linkai_billing.domain.errors import InvalidToken
from linkai_billing.infra.config import get_settings


class PyJwtVerifier:
    def __init__(self, *, secret: str | None = None) -> None:
        self._secret = secret or get_settings().jwt_secret

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise InvalidToken(f"访问令牌无效: {exc}") from exc
        user_id = claims.get("sub")
        tenant_id = claims.get("tid")
        if not isinstance(user_id, str) or not isinstance(tenant_id, str):
            raise InvalidToken("令牌缺少 sub/tid claims")
        return Principal(user_id=user_id, tenant_id=tenant_id)
