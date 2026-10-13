"""FastAPI 应用工厂。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from linkai_model_proxy.api.dependencies import AppContainer, get_container
from linkai_model_proxy.api.routers import chat, health, playground
from linkai_model_proxy.domain.errors import DomainError

API_TITLE = "LinkAI Model Proxy"
API_VERSION = "0.1.0"


class TraceIdMiddleware(BaseHTTPMiddleware):
    """把trace_id 贯通到响应头（docs/observability.md 约定）。

    入站已有 `X-Trace-Id` 则沿用（网关已注入），否则新生成——
    保证全链路同一个 trace_id，跨服务对账才做得到。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or request.headers.get("X-Request-Id")
        response = await call_next(request)
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动时建依赖容器，关闭时释放出网连接。"""
    container: AppContainer = get_container()
    app.state.container = container
    try:
        yield
    finally:
        await container.aclose()


def create_app() -> FastAPI:
    """构造 FastAPI 应用。"""
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=(
            "统一 OpenAI 兼容模型网关：厂商适配器注册中心 + 降级链 + token 计量埋点。\n\n"
            "所有厂商调用统一经本服务出网（受 SSRF 闸门约束），无厂商 SDK 直连。"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(TraceIdMiddleware)

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        """领域异常 → 契约 `Error` 形态（`schemas/common.yaml#/Error`）。

        状态码由异常的 `client_status` 决定，不用 `retriable` 推导——
        两者语义正交（见 domain/errors.py 的说明）。
        """
        return JSONResponse(
            status_code=exc.client_status,
            content={
                "code": exc.code,
                "message": str(exc),
                "requestId": _request_id(),
            },
        )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(playground.router)
    return app


def _request_id() -> str:
    """错误体的 requestId——排障用链路追踪 ID。"""
    from uuid import uuid4

    return uuid4().hex


app = create_app()
