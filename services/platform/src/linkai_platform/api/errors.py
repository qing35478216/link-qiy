"""统一错误响应（契约 common.yaml#/Error：code/message/requestId/details）与异常处理器。

映射：
- AgreementNotAccepted → 403
- InvalidSmsCode / RefreshTokenRevoked → 401（认证失败类）
- InvalidToken → 401
- InvalidPhone / InvalidNickname / 请求校验失败 → 400/422
- UserNotFound → 404
- TenantMismatch（本文件定义）→ 403
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from linkai_platform.domain.auth import (
    AgreementNotAccepted,
    AuthError,
    InvalidToken,
)
from linkai_platform.domain.users import DomainError, UserNotFound


class TenantMismatch(Exception):
    """X-Tenant-Id 头与令牌 tid 不一致（铁律 6 的服务侧 enforcement）。"""


def _request_id(request: Request) -> str:
    header = request.headers.get("X-Request-Id")
    return header or uuid.uuid4().hex


def _error_body(code: str, message: str, request: Request, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "requestId": _request_id(request)}
    if details is not None:
        body["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgreementNotAccepted)
    async def _agreement(request: Request, exc: AgreementNotAccepted) -> JSONResponse:
        return JSONResponse(status_code=403, content=_error_body(exc.code, str(exc), request))

    @app.exception_handler(TenantMismatch)
    async def _tenant(request: Request, exc: TenantMismatch) -> JSONResponse:
        return JSONResponse(
            status_code=403, content=_error_body("TENANT_MISMATCH", str(exc), request)
        )

    @app.exception_handler(AuthError)
    async def _auth(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(status_code=401, content=_error_body(exc.code, str(exc), request))

    @app.exception_handler(InvalidToken)
    async def _invalid_token(request: Request, exc: InvalidToken) -> JSONResponse:
        return JSONResponse(status_code=401, content=_error_body(exc.code, str(exc), request))

    @app.exception_handler(UserNotFound)
    async def _not_found(request: Request, exc: UserNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404, content=_error_body("USER_NOT_FOUND", str(exc), request)
        )

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=400, content=_error_body(type(exc).__name__, str(exc), request)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 只取可序列化字段（ctx 可能携带异常对象，不能进 JSON）
        details = [
            {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", "请求参数校验失败", request, details=details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "HTTP 错误"
        return JSONResponse(
            status_code=exc.status_code, content=_error_body("HTTP_ERROR", message, request)
        )
