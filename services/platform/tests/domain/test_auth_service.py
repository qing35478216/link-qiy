"""认证编排领域单测：双方式登录、协议拒绝、JWT 刷新/登出/篡改/过期。"""

from __future__ import annotations

import pytest

from linkai_platform.domain.auth import (
    AgreementNotAccepted,
    InvalidSmsCode,
    InvalidToken,
    Principal,
    RefreshTokenRevoked,
)
from linkai_platform.domain.events import DomainEvent, UserCreated
from linkai_platform.infra.bus import InMemoryMessageBus
from linkai_platform.infra.jwt_service import PyJwtTokenService
from linkai_platform.infra.sms_code_store import InMemorySmsCodeStore
from linkai_platform.infra.sms_mock import MockSmsProvider
from linkai_platform.infra.wechat_mock import MockWechatProvider
from linkai_platform.services.auth_service import AuthService
from tests.conftest import FakeAccountDirectory, FakeRefreshTokenStore, FakeUserRepository

SECRET = "test-secret-0123456789abcdef0123456789abcdef"  # noqa: S105 - ≥32 字节测试密钥（RFC 7518）


def make_service(
    *,
    users: FakeUserRepository | None = None,
    directory: FakeAccountDirectory | None = None,
    refresh_store: FakeRefreshTokenStore | None = None,
    sms_codes: InMemorySmsCodeStore | None = None,
    tokens: PyJwtTokenService | None = None,
    wechat: MockWechatProvider | None = None,
    bus: InMemoryMessageBus | None = None,
) -> tuple[AuthService, list[DomainEvent]]:
    bus = bus or InMemoryMessageBus()
    events: list[DomainEvent] = []
    bus.subscribe(events.append)
    service = AuthService(
        users=users or FakeUserRepository(),
        directory=directory or FakeAccountDirectory(),
        refresh_store=refresh_store or FakeRefreshTokenStore(),
        sms_codes=sms_codes or InMemorySmsCodeStore(),
        tokens=tokens
        or PyJwtTokenService(secret=SECRET, access_ttl_seconds=3600, refresh_ttl_seconds=86400),
        wechat=wechat or MockWechatProvider(),
        sms=MockSmsProvider(),
        bus=bus,
    )
    return service, events


# —— 手机号登录 ——


def test_phone_login_new_user_publishes_event() -> None:
    sms_codes = InMemorySmsCodeStore()
    service, events = make_service(sms_codes=sms_codes)
    service.send_sms_code("13800138000", "login")
    code = sms_codes.peek_code("13800138000")
    assert code is not None

    user, pair, is_new = service.login_by_phone(
        phone="13800138000", sms_code=code, agreement_accepted=True
    )
    assert is_new is True
    assert user.agreement_accepted_at is not None
    assert pair.access_token and pair.refresh_token and pair.expires_in == 3600
    assert len(events) == 1 and isinstance(events[0], UserCreated)
    assert events[0].payload["phone"] == "13800138000"


def test_phone_login_existing_user_no_duplicate_event() -> None:
    sms_codes = InMemorySmsCodeStore()
    users, directory = FakeUserRepository(), FakeAccountDirectory()
    service, events = make_service(sms_codes=sms_codes, users=users, directory=directory)
    service.send_sms_code("13800138000", "login")
    service.login_by_phone(
        phone="13800138000",
        sms_code=sms_codes.peek_code("13800138000") or "",
        agreement_accepted=True,
    )
    service.send_sms_code("13800138000", "login")
    user2, _, is_new = service.login_by_phone(
        phone="13800138000",
        sms_code=sms_codes.peek_code("13800138000") or "",
        agreement_accepted=True,
    )
    assert is_new is False
    assert user2.id == users.get(user2.tenant_id, user2.id).id  # type: ignore[union-attr]
    assert len(events) == 1  # 只发一次 UserCreated


def test_phone_login_agreement_not_accepted_rejected() -> None:
    service, events = make_service()
    with pytest.raises(AgreementNotAccepted):
        service.login_by_phone(phone="13800138000", sms_code="000000", agreement_accepted=False)
    assert events == []  # 协议校验在最前，无副作用


def test_phone_login_wrong_code_rejected() -> None:
    sms_codes = InMemorySmsCodeStore()
    service, _ = make_service(sms_codes=sms_codes)
    service.send_sms_code("13800138000", "login")
    with pytest.raises(InvalidSmsCode):
        service.login_by_phone(phone="13800138000", sms_code="999999", agreement_accepted=True)


def test_phone_login_code_single_use() -> None:
    sms_codes = InMemorySmsCodeStore()
    service, _ = make_service(sms_codes=sms_codes)
    service.send_sms_code("13800138000", "login")
    code = sms_codes.peek_code("13800138000") or ""
    service.login_by_phone(phone="13800138000", sms_code=code, agreement_accepted=True)
    service.send_sms_code("13800138000", "login")
    with pytest.raises(InvalidSmsCode):  # 旧码已随成功清除
        service.login_by_phone(phone="13800138000", sms_code=code, agreement_accepted=True)


# —— 微信扫码登录 ——


def test_wechat_login_flow() -> None:
    wechat = MockWechatProvider()
    service, events = make_service(wechat=wechat)
    ticket, qr_url, _ = service.create_wechat_qrcode("login")
    assert qr_url.endswith(ticket)

    assert service.poll_wechat_qrcode(ticket).status == "pending"
    wechat.mark_scanned(ticket)
    assert service.poll_wechat_qrcode(ticket).status == "scanned"
    wechat.confirm(ticket, "openid-user-1")

    status = service.poll_wechat_qrcode(ticket)
    assert status.status == "confirmed" and status.openid == "openid-user-1"

    user, _, is_new = service.login_by_wechat_openid(status.openid or "")
    assert is_new is True
    assert user.wechat_openid == "openid-user-1"
    assert len(events) == 1 and isinstance(events[0], UserCreated)
    assert events[0].payload["wechat_openid"] == "openid-user-1"

    # 再次登录：同用户，不再发事件
    user2, _, is_new2 = service.login_by_wechat_openid("openid-user-1")
    assert is_new2 is False and user2.id == user.id
    assert len(events) == 1


def test_wechat_unknown_ticket_expired() -> None:
    service, _ = make_service()
    assert service.poll_wechat_qrcode("no-such-ticket").status == "expired"


def test_wechat_auto_confirm_mock() -> None:
    import time

    wechat = MockWechatProvider(auto_confirm_seconds=0.1)
    service, _ = make_service(wechat=wechat)
    ticket, _, _ = service.create_wechat_qrcode("login")
    # 自动确认模式下首轮轮询即视为已扫码（mock 状态机自动推进）
    assert service.poll_wechat_qrcode(ticket).status == "scanned"
    time.sleep(0.5)
    status = service.poll_wechat_qrcode(ticket)
    assert status.status == "confirmed" and status.openid is not None


# —— JWT 生命周期 ——


def _login(service: AuthService, sms_codes: InMemorySmsCodeStore) -> tuple[str, str]:
    service.send_sms_code("13800138000", "login")
    _, pair, _ = service.login_by_phone(
        phone="13800138000",
        sms_code=sms_codes.peek_code("13800138000") or "",
        agreement_accepted=True,
    )
    return pair.access_token, pair.refresh_token


def test_refresh_rotates_and_old_refresh_revoked() -> None:
    sms_codes = InMemorySmsCodeStore()
    service, _ = make_service(sms_codes=sms_codes)
    _, refresh = _login(service, sms_codes)

    new_pair = service.refresh(refresh)
    assert new_pair.access_token != ""
    with pytest.raises(RefreshTokenRevoked):  # 旧 refresh 已轮换吊销
        service.refresh(refresh)
    # 新 refresh 可用
    newer = service.refresh(new_pair.refresh_token)
    assert newer.access_token != ""


def test_logout_revokes_all_user_refresh_tokens() -> None:
    sms_codes = InMemorySmsCodeStore()
    service, _ = make_service(sms_codes=sms_codes)
    _, refresh = _login(service, sms_codes)
    tokens = service._tokens
    claims = tokens.verify(refresh, "refresh")
    service.logout(claims.principal)
    with pytest.raises(RefreshTokenRevoked):
        service.refresh(refresh)


def test_tampered_token_rejected() -> None:
    service, _ = make_service()
    tokens = PyJwtTokenService(secret=SECRET)
    raw, _ = tokens.issue(Principal(user_id="u1", tenant_id="t1"), "access")
    header, _, signature = raw.rpartition(".")
    forged = f"{header}.eyJzdWIiOiJ1MiJ9.{signature}"  # 篡改 payload，签名不变
    with pytest.raises(InvalidToken):
        service._tokens.verify(forged, "access")


def test_expired_access_token_rejected() -> None:
    issuer = PyJwtTokenService(secret=SECRET, access_ttl_seconds=3600, refresh_ttl_seconds=86400)
    expired_checker = PyJwtTokenService(
        secret=SECRET,
        access_ttl_seconds=3600,
        refresh_ttl_seconds=86400,
        leeway_seconds=-7200,  # 负 leeway 模拟"已过期两小时"
    )
    raw, _ = issuer.issue(Principal(user_id="u1", tenant_id="t1"), "access")
    with pytest.raises(InvalidToken):
        expired_checker.verify(raw, "access")


def test_access_token_cannot_be_used_as_refresh() -> None:
    sms_codes = InMemorySmsCodeStore()
    service, _ = make_service(sms_codes=sms_codes)
    access, _ = _login(service, sms_codes)
    with pytest.raises(InvalidToken):
        service.refresh(access)
