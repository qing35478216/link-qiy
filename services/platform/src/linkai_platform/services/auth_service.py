"""认证编排（应用层）：把 domain 规则与 infra 接口组装成用例。

职责：
- 微信扫码：创建票据 → 轮询 → confirmed 后登录/注册（发 UserCreated）
- 手机号：发码 → 校验码 + 协议勾选 → 登录/注册
- JWT：refresh（轮换：吊销旧 jti、发新对）、logout（吊销 jti）
事务边界与事件发布在本层；本类不 import fastapi/sqlalchemy。
"""

from __future__ import annotations

from datetime import datetime

import structlog

from linkai_platform.domain import rules
from linkai_platform.domain.auth import (
    InvalidSmsCode,
    Principal,
    QrStatus,
    SmsProvider,
    TokenPair,
    TokenService,
    WechatProvider,
    generate_sms_code,
)
from linkai_platform.domain.events import MessageBus, UserCreated
from linkai_platform.domain.repositories import (
    AccountDirectory,
    AccountRef,
    RefreshTokenRecord,
    RefreshTokenStore,
    SmsCodeStore,
    UserRepository,
)
from linkai_platform.domain.users import User

logger = structlog.get_logger(__name__)


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        directory: AccountDirectory,
        refresh_store: RefreshTokenStore,
        sms_codes: SmsCodeStore,
        tokens: TokenService,
        wechat: WechatProvider,
        sms: SmsProvider,
        bus: MessageBus,
        access_ttl_seconds: int = 3600,
        refresh_ttl_seconds: int = 30 * 24 * 3600,
        sms_code_ttl_seconds: int = 300,
        qr_ttl_seconds: int = 300,
    ) -> None:
        self._users = users
        self._directory = directory
        self._refresh_store = refresh_store
        self._sms_codes = sms_codes
        self._tokens = tokens
        self._wechat = wechat
        self._sms = sms
        self._bus = bus
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds
        self._sms_code_ttl = sms_code_ttl_seconds
        self._qr_ttl = qr_ttl_seconds

    # —— 微信扫码 ——

    def create_wechat_qrcode(self, scene: str) -> tuple[str, str, datetime]:
        """返回 (ticket, qr_url, expires_at datetime)。"""
        ticket = self._wechat.create_qrcode(scene, self._qr_ttl)
        return (ticket.ticket, ticket.qr_url, ticket.expires_at)

    def poll_wechat_qrcode(self, ticket: str) -> QrStatus:
        return self._wechat.poll(ticket)

    def login_by_wechat_openid(self, openid: str) -> tuple[User, TokenPair, bool]:
        """openid 登录/注册（扫码 confirmed 后由 api 层调用）。返回 (user, tokens, is_new)。"""
        ref = self._directory.find_by_openid(openid)
        if ref is not None:
            user = self._users.get(ref.tenant_id, ref.user_id)
            if user is not None:
                return user, self._issue_token_pair(user), False
            logger.error("account_directory_orphan", openid=openid)
        user = User.register_with_wechat(openid)
        self._persist_new_user(user, phone=None, openid=openid)
        return user, self._issue_token_pair(user), True

    # —— 手机号 ——

    def send_sms_code(self, phone: str, scene: str) -> None:
        code = generate_sms_code()
        self._sms_codes.save(phone, code, self._sms_code_ttl)
        self._sms.send_code(phone, code, scene)
        logger.info("sms_code_sent", phone=phone[-4:], scene=scene)

    def login_by_phone(
        self, *, phone: str, sms_code: str, agreement_accepted: bool
    ) -> tuple[User, TokenPair, bool]:
        """手机号登录。协议未勾选抛 AgreementNotAccepted（403）。"""
        rules.require_agreement(agreement_accepted)
        if not self._sms_codes.verify(phone, sms_code):
            raise InvalidSmsCode("验证码错误或已过期")
        ref = self._directory.find_by_phone(phone)
        if ref is not None:
            user = self._users.get(ref.tenant_id, ref.user_id)
            if user is not None:
                self._maybe_accept_agreement(user, agreement_accepted)
                return user, self._issue_token_pair(user), False
            logger.error("account_directory_orphan", phone=phone[-4:])
        user = User.register_with_phone(phone)
        user.accept_agreement()  # 登录即注册场景：本次请求已显式勾选
        self._persist_new_user(user, phone=phone, openid=None)
        return user, self._issue_token_pair(user), True

    # —— JWT 生命周期 ——

    def refresh(self, refresh_token: str) -> TokenPair:
        """刷新：校验 + 吊销旧 jti + 发新对（轮换，防重放）。"""
        claims = self._tokens.verify(refresh_token, "refresh")
        record = self._refresh_store.get(claims.jti)
        rules.assert_refresh_usable(record, claims)
        assert record is not None  # assert_refresh_usable 已保证非 None
        self._refresh_store.revoke(record.jti)
        return self._issue_token_pair_for(claims.principal)

    def logout(self, principal: Principal) -> None:
        """登出：吊销该用户全部刷新令牌（access token 短期，自然过期）。"""
        self._refresh_store.revoke_all_for_user(principal.user_id)

    # —— 内部 ——

    def _issue_token_pair(self, user: User) -> TokenPair:
        return self._issue_token_pair_for(Principal(user_id=user.id, tenant_id=user.tenant_id))

    def _issue_token_pair_for(self, principal: Principal) -> TokenPair:
        access, _ = self._tokens.issue(principal, "access")
        refresh, refresh_claims = self._tokens.issue(principal, "refresh")
        self._refresh_store.save(
            RefreshTokenRecord(
                jti=refresh_claims.jti,
                user_id=principal.user_id,
                expires_at=refresh_claims.expires_at,
            )
        )
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=self._access_ttl)

    def _persist_new_user(self, user: User, *, phone: str | None, openid: str | None) -> None:
        self._users.add(user)
        self._directory.register(phone=phone, openid=openid, ref=self._ref_of(user))
        self._bus.publish(
            UserCreated(
                user_id=user.id,
                tenant_id=user.tenant_id,
                phone=phone,
                wechat_openid=openid,
            )
        )

    def _maybe_accept_agreement(self, user: User, accepted: bool) -> None:
        if rules.touch_agreement_acceptance(accepted, user.agreement_accepted_at):
            user.accept_agreement()
            self._users.save(user)

    @staticmethod
    def _ref_of(user: User) -> AccountRef:
        return AccountRef(tenant_id=user.tenant_id, user_id=user.id)
