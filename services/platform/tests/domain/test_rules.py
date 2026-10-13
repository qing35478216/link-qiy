"""领域规则单测：协议勾选、刷新令牌可用性。"""

from __future__ import annotations

from datetime import timedelta

import pytest

from linkai_platform.domain import rules
from linkai_platform.domain.auth import (
    AgreementNotAccepted,
    InvalidToken,
    Principal,
    RefreshTokenRevoked,
    TokenClaims,
)
from linkai_platform.domain.repositories import RefreshTokenRecord
from linkai_platform.domain.users import utcnow


def _claims(user_id: str = "u1") -> TokenClaims:
    return TokenClaims(
        principal=Principal(user_id=user_id, tenant_id="t1"),
        kind="refresh",
        jti="jti-1",
        expires_at=utcnow() + timedelta(days=1),
    )


def _record(
    user_id: str = "u1", revoked: bool = False, expired: bool = False
) -> RefreshTokenRecord:
    expires = utcnow() - timedelta(seconds=1) if expired else utcnow() + timedelta(days=1)
    return RefreshTokenRecord(jti="jti-1", user_id=user_id, expires_at=expires, revoked=revoked)


def test_require_agreement_rejects() -> None:
    with pytest.raises(AgreementNotAccepted) as exc_info:
        rules.require_agreement(False)
    assert exc_info.value.code == "AGREEMENT_NOT_ACCEPTED"


def test_require_agreement_passes() -> None:
    rules.require_agreement(True)


def test_touch_agreement_acceptance() -> None:
    assert rules.touch_agreement_acceptance(True, None) is True
    already = utcnow()
    assert rules.touch_agreement_acceptance(True, already) is False
    assert rules.touch_agreement_acceptance(False, None) is False


def test_assert_refresh_usable_ok() -> None:
    rules.assert_refresh_usable(_record(), _claims())


def test_assert_refresh_usable_unknown() -> None:
    with pytest.raises(InvalidToken):
        rules.assert_refresh_usable(None, _claims())


def test_assert_refresh_usable_revoked() -> None:
    with pytest.raises(RefreshTokenRevoked):
        rules.assert_refresh_usable(_record(revoked=True), _claims())


def test_assert_refresh_usable_expired() -> None:
    with pytest.raises(RefreshTokenRevoked):
        rules.assert_refresh_usable(_record(expired=True), _claims())


def test_assert_refresh_usable_owner_mismatch() -> None:
    with pytest.raises(InvalidToken):
        rules.assert_refresh_usable(_record(user_id="u2"), _claims(user_id="u1"))
