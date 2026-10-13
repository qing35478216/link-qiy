"""用户实体领域规则单测。"""

from __future__ import annotations

import pytest

from linkai_platform.domain.users import (
    InvalidNickname,
    InvalidOpenid,
    InvalidPhone,
    Plan,
    User,
    validate_phone,
)


def test_register_with_phone_defaults() -> None:
    user = User.register_with_phone("13800138000")
    assert user.tenant_id == user.id  # Phase 0：个人租户
    assert user.plan is Plan.BASIC
    assert user.nickname == "用户8000"
    assert user.agreement_accepted_at is None


def test_register_with_phone_custom_nickname() -> None:
    user = User.register_with_phone("13911112222", nickname="小明")
    assert user.nickname == "小明"


@pytest.mark.parametrize("bad", ["", "123", "23800138000", "1380013800a", " 13800138000 "])
def test_validate_phone_rejects(bad: str) -> None:
    with pytest.raises(InvalidPhone):
        validate_phone(bad)


def test_register_with_wechat() -> None:
    user = User.register_with_wechat("mock-openid-abc")
    assert user.wechat_openid == "mock-openid-abc"
    assert user.tenant_id == user.id


def test_register_with_wechat_rejects_empty() -> None:
    with pytest.raises(InvalidOpenid):
        User.register_with_wechat("")


def test_accept_agreement_idempotent() -> None:
    user = User.register_with_phone("13800138000")
    user.accept_agreement()
    first = user.agreement_accepted_at
    assert first is not None
    user.accept_agreement()
    assert user.agreement_accepted_at == first  # 不重复刷新


def test_update_profile_partial() -> None:
    user = User.register_with_phone("13800138000")
    original_phone = user.phone
    user.update_profile(nickname="新昵称")
    assert user.nickname == "新昵称"
    assert user.phone == original_phone  # 未传字段不修改


def test_update_profile_nickname_bounds() -> None:
    user = User.register_with_phone("13800138000")
    with pytest.raises(InvalidNickname):
        user.update_profile(nickname="")


def test_update_profile_phone_validation() -> None:
    user = User.register_with_phone("13800138000")
    with pytest.raises(InvalidPhone):
        user.update_profile(phone="abc")
