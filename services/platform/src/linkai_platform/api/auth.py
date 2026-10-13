"""Auth 路由（契约 /auth/* 段，security: [] 公开端点）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from linkai_platform.api.deps import AppContext, get_context, get_principal
from linkai_platform.api.schemas import (
    CreateWechatQrcodeRequest,
    CreateWechatQrcodeResponse,
    PhoneLoginRequest,
    RefreshTokenRequest,
    SendSmsCodeRequest,
    TokenPairResponse,
    WechatQrcodeStatusResponse,
)
from linkai_platform.domain.auth import Principal, TokenPair

router = APIRouter(tags=["Auth"])


def _to_token_response(pair: TokenPair) -> TokenPairResponse:
    return TokenPairResponse(
        accessToken=pair.access_token,
        refreshToken=pair.refresh_token,
        expiresIn=pair.expires_in,
        tokenType=pair.token_type,
    )


@router.post("/auth/wechat/qrcode", response_model=CreateWechatQrcodeResponse)
async def create_wechat_qrcode(
    body: CreateWechatQrcodeRequest, ctx: AppContext = Depends(get_context)
) -> CreateWechatQrcodeResponse:
    ticket, qr_url, expires_at = ctx.auth_service.create_wechat_qrcode(body.scene)
    return CreateWechatQrcodeResponse(ticket=ticket, qrUrl=qr_url, expiresAt=expires_at)


@router.get("/auth/wechat/qrcode/{ticket}", response_model=WechatQrcodeStatusResponse)
async def get_wechat_qrcode_status(
    ticket: str, ctx: AppContext = Depends(get_context)
) -> WechatQrcodeStatusResponse:
    status = ctx.auth_service.poll_wechat_qrcode(ticket)
    tokens: TokenPairResponse | None = None
    if status.openid is not None:  # confirmed：服务端完成登录/注册并签发令牌
        _, pair, _ = ctx.auth_service.login_by_wechat_openid(status.openid)
        tokens = _to_token_response(pair)
    return WechatQrcodeStatusResponse(status=status.status, tokens=tokens)


@router.post("/auth/phone/sms-code", status_code=204)
async def send_sms_code(
    body: SendSmsCodeRequest, ctx: AppContext = Depends(get_context)
) -> Response:
    ctx.auth_service.send_sms_code(body.phone, body.scene)
    return Response(status_code=204)


@router.post("/auth/phone/login", response_model=TokenPairResponse)
async def login_by_phone(
    body: PhoneLoginRequest, ctx: AppContext = Depends(get_context)
) -> TokenPairResponse:
    _, pair, _ = ctx.auth_service.login_by_phone(
        phone=body.phone, sms_code=body.smsCode, agreement_accepted=body.agreementAccepted
    )
    return _to_token_response(pair)


@router.post("/auth/refresh", response_model=TokenPairResponse)
async def refresh_token(
    body: RefreshTokenRequest, ctx: AppContext = Depends(get_context)
) -> TokenPairResponse:
    return _to_token_response(ctx.auth_service.refresh(body.refreshToken))


@router.post("/auth/logout", status_code=204)
async def logout(
    principal: Principal = Depends(get_principal), ctx: AppContext = Depends(get_context)
) -> Response:
    """登出（bearerAuth）：吊销该用户全部刷新令牌。"""
    ctx.auth_service.logout(principal)
    return Response(status_code=204)
