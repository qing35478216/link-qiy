"""LinkAI billing 服务入口（四层架构：api -> services -> domain <- infra）。

约定：
- 健康检查 GET /healthz（api/health.py），compose / K8s probe 统一指向它
- OTel FastAPI 自动插桩：所有请求自动带 trace_id（docs/observability.md）
- Schema 由 Alembic 管理（alembic/versions/0001_billing.py）；启动不自动建表
- DB 会话每请求一个（api/deps.get_context 负责 commit/rollback/close）；
  无状态件（事件流水/Mock 支付/JWT 校验器）跨请求共享，从 app.state 取
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from linkai_billing.api import internal as internal_api
from linkai_billing.api import orders as orders_api
from linkai_billing.api import quota as quota_api
from linkai_billing.api import usage as usage_api
from linkai_billing.api import wallet as wallet_api
from linkai_billing.api.deps import build_stream
from linkai_billing.api.errors import register_exception_handlers
from linkai_billing.api.health import router as health_router
from linkai_billing.infra.config import Settings, get_settings
from linkai_billing.infra.db import make_engine, make_session_factory
from linkai_billing.infra.jwt_service import PyJwtVerifier
from linkai_billing.infra.logging import setup_logging
from linkai_billing.infra.payment_mock import MockPaymentProvider

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(app.state.settings.service_name, app.state.settings.log_level)
    logger.info(
        "billing_service_started",
        redis=bool(app.state.settings.redis_url),
        msg="事件流水: Redis Streams" if app.state.settings.redis_url else "事件流水: 内存实现",
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    if cfg.jwt_secret_is_default:
        logger.warning("jwt_secret_using_default", msg="生产环境必须注入 LINKAI_JWT_SECRET")

    app = FastAPI(title="linkai-billing", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(wallet_api.router)
    app.include_router(orders_api.router)
    app.include_router(usage_api.router)
    app.include_router(quota_api.router)
    app.include_router(internal_api.router)

    # —— 跨请求共享件；每请求组装见 api/deps.get_context ——
    app.state.settings = cfg
    app.state.session_factory = make_session_factory(make_engine(cfg.database_url))
    app.state.verifier = PyJwtVerifier(secret=cfg.jwt_secret)
    app.state.payment = MockPaymentProvider(secret=cfg.payment_mock_secret)
    app.state.stream = build_stream(cfg)

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
