"""FastAPI 依赖：每请求组装（AppContext）、事务边界与鉴权依赖。

AppContext 每请求新建（DB 会话生命周期 = 请求生命周期）；内存态组件从
app.state 共享。测试可替换 app.state 上的任意组件。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from linkai_platform.api.errors import TenantMismatch
from linkai_platform.domain.auth import InvalidToken, Principal, TokenService
from linkai_platform.domain.events import MessageBus
from linkai_platform.domain.repositories import (
    AccountDirectory,
    RefreshTokenStore,
    SmsCodeStore,
    UserRepository,
)
from linkai_platform.infra.account_directory import SqlAlchemyAccountDirectory
from linkai_platform.infra.refresh_store import SqlAlchemyRefreshTokenStore
from linkai_platform.infra.user_repo import SqlAlchemyUserRepository
from linkai_platform.infra.wechat_mock import MockWechatProvider
from linkai_platform.services.auth_service import AuthService
from linkai_platform.services.user_service import UserService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AppContext:
    """单次请求的应用组装体。"""

    tokens: TokenService
    users: UserRepository
    directory: AccountDirectory
    refresh_store: RefreshTokenStore
    sms_codes: SmsCodeStore
    bus: MessageBus
    auth_service: AuthService
    user_service: UserService
    wechat_provider: MockWechatProvider  # 测试/联调驱动扫码状态机
    session: Session


def get_context(request: Request) -> Iterator[AppContext]:
    """请求级组装 + 事务边界：正常返回 commit，异常 rollback，最后关会话。"""
    state = request.app.state
    cfg = state.settings
    session: Session = state.session_factory()
    try:
        users = SqlAlchemyUserRepository(session)
        directory = SqlAlchemyAccountDirectory(session)
        refresh_store = SqlAlchemyRefreshTokenStore(session)
        auth_service = AuthService(
            users=users,
            directory=directory,
            refresh_store=refresh_store,
            sms_codes=state.sms_codes,
            tokens=state.tokens,
            wechat=state.wechat_provider,
            sms=state.sms_provider,
            bus=state.bus,
            access_ttl_seconds=cfg.access_token_ttl_seconds,
            refresh_ttl_seconds=cfg.refresh_token_ttl_seconds,
            sms_code_ttl_seconds=cfg.sms_code_ttl_seconds,
            qr_ttl_seconds=cfg.qr_ttl_seconds,
        )
        yield AppContext(
            tokens=state.tokens,
            users=users,
            directory=directory,
            refresh_store=refresh_store,
            sms_codes=state.sms_codes,
            bus=state.bus,
            auth_service=auth_service,
            user_service=UserService(users=users),
            wechat_provider=state.wechat_provider,
            session=session,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    ctx: AppContext = Depends(get_context),
) -> Principal:
    """解析 Bearer → Principal；有 X-Tenant-Id 时必须与令牌 tid 一致（铁律 6）。"""
    if credentials is None:
        raise InvalidToken("缺少 Bearer 令牌")
    claims = ctx.tokens.verify(credentials.credentials, "access")
    if x_tenant_id is not None and x_tenant_id != claims.principal.tenant_id:
        raise TenantMismatch("X-Tenant-Id 与令牌租户不一致")
    return claims.principal
