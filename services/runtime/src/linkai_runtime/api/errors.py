"""统一错误响应（契约 common.yaml#/Error：code/message/requestId）与异常处理器。

用户面直接暴露给第三方（嵌入 SDK / 渠道 / 第三方工具），5xx 会被外部看到，
因此：领域异常一律转契约 Error 信封；状态码由异常的 client_status 决定。
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from linkai_runtime.domain.errors import DomainError


def _request_id(request: Request) -> str:
    header = request.headers.get("X-Request-Id")
    return header or uuid.uuid4().hex


def _error_body(
    code: str, message: str, request: Request, details: object = None
) -> dict[str, object]:
    body: dict[str, object] = {"code": code, "message": message, "requestId": _request_id(request)}
    if details is not None:
        body["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        """领域异常 → 契约 Error 信封；状态码取 client_status（429 配额等）。"""
        return JSONResponse(
            status_code=exc.client_status,
            content=_error_body(exc.code, str(exc), request),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 只取可序列化字段（ctx 可能携带异常对象，不能进 JSON）
        details: list[dict[str, object]] = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", "请求参数校验失败", request, details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "HTTP 错误"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("HTTP_ERROR", message, request),
        )
