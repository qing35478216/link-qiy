"""FastAPI 依赖注入与应用装配（四层架构的"接线板"）。

这里才知道具体的 infra 实现；api 层因此保持只做协议转换。
容器可整体注入（测试替换任意端口实现），无全局单例——避免用例间状态泄漏。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from linkai_runtime.domain.errors import UnauthorizedError
from linkai_runtime.domain.ports import TenantIdentity
from linkai_runtime.infra.api_key_store import DbApiKeyResolver
from linkai_runtime.infra.app_profile_provider import (
    PlatformHttpAppProfileProvider,
    StaticAppProfileProvider,
)
from linkai_runtime.infra.config import Settings, get_settings
from linkai_runtime.infra.conversation_repo import SqlAlchemyConversationRepository
from linkai_runtime.infra.db import Base, make_engine, make_session_factory
from linkai_runtime.infra.memory import NoopKnowledgeRetriever
from linkai_runtime.infra.model_proxy_client import HttpModelGateway
from linkai_runtime.infra.quota_guard import InMemoryQuotaGuard
from linkai_runtime.infra.trace_repo import SqlAlchemyExecutionTraceRepository
from linkai_runtime.services.chat_service import ChatService

bearer_scheme = HTTPBearer(auto_error=False)

#: API Key 长度上限（防内存放大/探测）
MAX_API_KEY_LEN = 512

#: 应用设定提供者的两种实现（按 settings.app_profile_source 选择）
ProfileProvider = StaticAppProfileProvider | PlatformHttpAppProfileProvider


@dataclass(frozen=True, slots=True)
class AppContainer:
    """应用级依赖容器（每进程一份；测试可自造替换端口）。"""

    settings: Settings
    session_factory: sessionmaker[Session]
    chat_service: ChatService
    api_keys: DbApiKeyResolver
    gateway: HttpModelGateway
    profiles: ProfileProvider

    async def aclose(self) -> None:
        await self.gateway.aclose()
        if isinstance(self.profiles, PlatformHttpAppProfileProvider):
            await self.profiles.aclose()


def build_container(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
) -> AppContainer:
    """组装完整依赖图（组装根：唯一同时知道 infra 具体类型的地方）。"""
    cfg = settings or get_settings()
    factory = session_factory or make_session_factory(make_engine(cfg.database_url))

    if cfg.app_profile_source == "platform":
        profiles: ProfileProvider = PlatformHttpAppProfileProvider(
            cfg.platform_base_url,
            service_token=cfg.service_token,
            timeout_seconds=cfg.http_timeout_seconds,
        )
    else:
        profiles = StaticAppProfileProvider(cfg.static_app_profiles)

    gateway = HttpModelGateway(
        cfg.model_proxy_base_url,
        timeout_seconds=cfg.http_timeout_seconds,
        connect_timeout_seconds=cfg.http_connect_timeout_seconds,
    )
    return AppContainer(
        settings=cfg,
        session_factory=factory,
        api_keys=DbApiKeyResolver(factory),
        gateway=gateway,
        profiles=profiles,
        chat_service=ChatService(
            conversations=SqlAlchemyConversationRepository(factory),
            traces=SqlAlchemyExecutionTraceRepository(factory),
            profiles=profiles,
            gateway=gateway,
            quota=InMemoryQuotaGuard(
                default_daily_tokens=cfg.quota_default_daily_tokens,
                tenant_daily_tokens=cfg.tenant_daily_tokens,
            ),
            knowledge=NoopKnowledgeRetriever(),
        ),
    )


def get_container(request: Request) -> AppContainer:
    """FastAPI 依赖：从 app.state 取容器（lifespan 装配）。"""
    container: AppContainer = request.app.state.container
    return container


ContainerDep = Annotated[AppContainer, Depends(get_container)]


async def get_caller(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    container: ContainerDep = None,  # type: ignore[assignment]
) -> TenantIdentity:
    """解析 Bearer API Key → 租户身份（用户面鉴权；铁律 6）。

    缺 Key / 无效 Key / 超长 Key 一律 401（统一错误信封，不区分原因防探测）。
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("缺少 Bearer API Key（Authorization: Bearer sk-...）")
    key = credentials.credentials
    if len(key) > MAX_API_KEY_LEN:
        raise UnauthorizedError("API Key 长度超限")
    identity = container.api_keys.resolve(key)
    if identity is None:
        raise UnauthorizedError("API Key 无效或已吊销")
    return identity


CallerDep = Annotated[TenantIdentity, Depends(get_caller)]


def resolve_trace_id(request: Request) -> str:
    """trace_id：入站 X-Trace-Id 沿用（网关注入），否则新生成（全链路贯通）。"""
    header = request.headers.get("X-Trace-Id") or request.headers.get("X-Request-Id")
    return header.strip() if header and header.strip() else uuid.uuid4().hex


__all__ = [
    "AppContainer",
    "Base",
    "CallerDep",
    "ContainerDep",
    "build_container",
    "get_caller",
    "get_container",
    "resolve_trace_id",
]
