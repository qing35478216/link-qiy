"""LinkAI platform 服务入口（四层架构：api -> services -> domain <- infra）。

约定：
- 健康检查 GET /healthz（api/health.py），compose / K8s probe 统一指向它
- OTel FastAPI 自动插桩：所有请求自动带 trace_id（docs/observability.md）
- Schema 由 Alembic 管理（alembic/versions/）；本服务启动不自动建表
- DB 会话每请求一个（api/deps.get_context 负责 commit/rollback/close）；
  内存态组件（扫码票据、验证码、事件总线、Mock Provider）跨请求共享
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from linkai_platform.api import apps as apps_api
from linkai_platform.api import auth as auth_api
from linkai_platform.api import quota as quota_api
from linkai_platform.api import users as users_api
from linkai_platform.api.errors import register_exception_handlers
from linkai_platform.api.health import router as health_router
from linkai_platform.infra.bus import InMemoryMessageBus
from linkai_platform.infra.config import Settings, get_settings
from linkai_platform.infra.db import make_engine, make_session_factory
from linkai_platform.infra.jwt_service import PyJwtTokenService
from linkai_platform.infra.logging import setup_logging
from linkai_platform.infra.sms_code_store import InMemorySmsCodeStore
from linkai_platform.infra.sms_mock import MockSmsProvider
from linkai_platform.infra.wechat_mock import MockWechatProvider

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(app.state.settings.service_name, app.state.settings.log_level)
    logger.info("platform_service_started")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    if cfg.jwt_secret_is_default:
        logger.warning("jwt_secret_using_default", msg="生产环境必须注入 LINKAI_JWT_SECRET")

    app = FastAPI(title="linkai-platform", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_api.router)
    app.include_router(users_api.router)
    app.include_router(apps_api.router)
    app.include_router(quota_api.router)

    # —— 跨请求共享的持久件（内存态组件 + 令牌服务）；每请求组装见 api/deps ——
    app.state.settings = cfg
    app.state.session_factory = make_session_factory(make_engine(cfg.database_url))
    app.state.tokens = PyJwtTokenService(
        secret=cfg.jwt_secret,
        access_ttl_seconds=cfg.access_token_ttl_seconds,
        refresh_ttl_seconds=cfg.refresh_token_ttl_seconds,
    )
    app.state.bus = InMemoryMessageBus()
    app.state.wechat_provider = MockWechatProvider(
        auto_confirm_seconds=cfg.wechat_mock_auto_confirm_seconds
    )
    app.state.sms_codes = InMemorySmsCodeStore()
    app.state.sms_provider = MockSmsProvider()

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
