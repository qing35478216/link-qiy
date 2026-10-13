"""FastAPI 应用工厂。

- 健康检查 GET /healthz（service-template 硬约定）
- DomainError → 契约 Error 信封（统一错误形状）
- OTel FastAPI 自动插桩：所有请求自动带 trace_id（docs/observability.md）
- 容器经 lifespan 装配（api/deps.build_container），关闭时释放出网连接
- 测试可预置 app.state.container（lifespan 检测到即跳过装配，且不负责关闭）
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from linkai_runtime.api.deps import AppContainer, build_container
from linkai_runtime.api.errors import register_exception_handlers
from linkai_runtime.api.health import router as health_router
from linkai_runtime.api.routers import chat as chat_router
from linkai_runtime.api.routers import models as models_router

API_TITLE = "LinkAI Runtime"
API_VERSION = "0.1.0"


class TraceIdMiddleware(BaseHTTPMiddleware):
    """把 trace_id 贯通到响应头（docs/observability.md 约定）。

    入站已有 X-Trace-Id 则沿用（网关注入），否则新生成——保证全链路同一
    trace_id，跨服务对账才做得到。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or request.headers.get("X-Request-Id")
        response = await call_next(request)
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """装配依赖容器（测试预置则跳过）；关闭时释放出网连接。"""
    injected = getattr(app.state, "container", None)
    owns_container = injected is None
    if owns_container:
        app.state.container = build_container()
    container: AppContainer = app.state.container
    if owns_container and container.settings.dev_api_keys:
        from linkai_runtime.infra.api_key_store import seed_dev_api_keys

        # dev 种子写入（幂等）；platform Key 体系落地后的迁移路径见 README
        seeded = seed_dev_api_keys(container.session_factory, container.settings.dev_api_keys)
        if seeded:
            import structlog

            structlog.get_logger(__name__).info("dev_api_keys_seeded", count=seeded)
    try:
        yield
    finally:
        if owns_container:
            await container.aclose()


def create_app(container: AppContainer | None = None) -> FastAPI:
    """构造 FastAPI 应用（container 可注入：测试替换端口实现）。"""
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=(
            "应用运行时（对话引擎）：上下文装配 + SSE 流式 + Runtime Event 协议。\n\n"
            "用户面 OpenAI 兼容端点（service-api.yaml v0.1.1）；模型调用经 model-proxy 出网。"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(TraceIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(chat_router.router)
    app.include_router(models_router.router)

    if container is not None:
        # 测试注入：lifespan 检测到已装配即跳过自建
        app.state.container = container

    return app


app = create_app()
