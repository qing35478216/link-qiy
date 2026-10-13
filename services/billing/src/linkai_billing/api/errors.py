"""统一错误响应（契约 common.yaml#/Error：code/message/requestId/details）。

映射（domain BillingError.http_status → HTTP）：
- InsufficientCredits → 402（积分不足，控制台引导充值）
- QuotaExceeded / FeatureNotAvailable / TenantMismatch → 403
- OrderNotFound / WalletNotFound → 404
- OrderStateError / DuplicateRequestId → 409
- PaymentVerifyError / InvalidToken → 401（安全事件，日志 ERROR 级）
- 其余 BillingError → 400
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from linkai_billing.domain.errors import BillingError, PaymentVerifyError

logger = structlog.get_logger(__name__)


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or uuid.uuid4().hex


def _error_body(
    code: str, message: str, request: Request, details: Any = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "requestId": _request_id(request)}
    if details:
        body["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BillingError)
    async def _billing(request: Request, exc: BillingError) -> JSONResponse:
        if isinstance(exc, PaymentVerifyError):
            # 安全事件：验签失败/重放——必须留痕告警
            logger.error(
                "payment.callback.rejected",
                code=exc.code,
                path=request.url.path,
                msg=str(exc),
            )
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, str(exc), request, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
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

    @app.exception_handler(ValueError)
    async def _value(request: Request, exc: ValueError) -> JSONResponse:
        # 领域不变量被破坏（如非法版本名/负数）——400，消息可读
        return JSONResponse(
            status_code=400, content=_error_body("INVALID_ARGUMENT", str(exc), request)
        )
