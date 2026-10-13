"""WechatProvider 的 Mock 实现（Phase 0；真实微信开放平台接入时新增 WechatOfficialProvider）。

行为：
- create_qrcode 生成 ticket + 伪 qrUrl（mock://wechat/qrcode/<ticket>）
- poll 按票据状态机返回 pending/scanned/confirmed/expired
- 可选自动确认（auto_confirm_seconds>0 时，到期自动置 confirmed 并发放 mock openid），
  仅用于本地联调与演示；生产置 0，由真实 Provider 的回调驱动状态
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from linkai_platform.domain.auth import QrStatus, QrTicket, WechatProvider, new_ticket_id
from linkai_platform.domain.users import utcnow

logger = structlog.get_logger(__name__)


class _TicketState:
    __slots__ = ("confirmed_at", "expires_at", "openid", "scanned_at")

    def __init__(self, expires_at: datetime) -> None:
        self.expires_at = expires_at
        self.scanned_at: datetime | None = None
        self.confirmed_at: datetime | None = None
        self.openid: str | None = None


class MockWechatProvider(WechatProvider):
    def __init__(
        self, *, auto_confirm_seconds: float = 0.0, qr_base_url: str = "mock://wechat/qrcode"
    ) -> None:
        self._auto_confirm = auto_confirm_seconds
        self._qr_base_url = qr_base_url
        self._tickets: dict[str, _TicketState] = {}

    def create_qrcode(self, scene: str, ttl_seconds: int) -> QrTicket:
        ticket = new_ticket_id()
        expires_at = utcnow() + timedelta(seconds=ttl_seconds)
        self._tickets[ticket] = _TicketState(expires_at)
        logger.info("mock_wechat_qrcode_created", ticket=ticket[:8], scene=scene)
        return QrTicket(
            ticket=ticket, qr_url=f"{self._qr_base_url}/{ticket}", expires_at=expires_at
        )

    def poll(self, ticket: str) -> QrStatus:
        state = self._tickets.get(ticket)
        if state is None:
            return QrStatus(status="expired")
        now = utcnow()
        if now >= state.expires_at:
            return QrStatus(status="expired")
        self._auto_drive(state, now)
        if state.confirmed_at is not None:
            return QrStatus(status="confirmed", openid=state.openid)
        if state.scanned_at is not None:
            return QrStatus(status="scanned")
        return QrStatus(status="pending")

    # —— 测试/联调驱动 ——

    def mark_scanned(self, ticket: str) -> None:
        """模拟用户已扫码（待确认）。"""
        state = self._require(ticket)
        if state.scanned_at is None:
            state.scanned_at = utcnow()

    def confirm(self, ticket: str, openid: str) -> None:
        """模拟用户在手机上确认登录（真实场景为微信回调）。"""
        state = self._require(ticket)
        state.openid = openid
        state.confirmed_at = utcnow()

    def _auto_drive(self, state: _TicketState, now: datetime) -> None:
        if self._auto_confirm <= 0 or state.confirmed_at is not None:
            return
        if state.scanned_at is None:
            state.scanned_at = now
        if (now - state.scanned_at).total_seconds() >= self._auto_confirm:
            state.openid = f"mock-openid-{utcnow().timestamp()}"
            state.confirmed_at = now
            logger.warning("mock_wechat_auto_confirmed", auto_confirm_seconds=self._auto_confirm)

    def _require(self, ticket: str) -> _TicketState:
        state = self._tickets.get(ticket)
        if state is None:
            raise KeyError(f"未知票据: {ticket}")
        return state
