from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.user_profile_plan import UserProfilePlan
from ..types import UNSET, Unset

T = TypeVar("T", bound="UserProfile")


@_attrs_define
class UserProfile:
    """
    Attributes:
        id (str | Unset):
        nickname (str | Unset):
        avatar_url (str | Unset):
        phone (str | Unset):
        plan (UserProfilePlan | Unset):
        agreement_accepted_at (datetime.datetime | Unset):
    """

    id: str | Unset = UNSET
    nickname: str | Unset = UNSET
    avatar_url: str | Unset = UNSET
    phone: str | Unset = UNSET
    plan: UserProfilePlan | Unset = UNSET
    agreement_accepted_at: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        nickname = self.nickname

        avatar_url = self.avatar_url

        phone = self.phone

        plan: str | Unset = UNSET
        if not isinstance(self.plan, Unset):
            plan = self.plan.value

        agreement_accepted_at: str | Unset = UNSET
        if not isinstance(self.agreement_accepted_at, Unset):
            agreement_accepted_at = self.agreement_accepted_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if nickname is not UNSET:
            field_dict["nickname"] = nickname
        if avatar_url is not UNSET:
            field_dict["avatarUrl"] = avatar_url
        if phone is not UNSET:
            field_dict["phone"] = phone
        if plan is not UNSET:
            field_dict["plan"] = plan
        if agreement_accepted_at is not UNSET:
            field_dict["agreementAcceptedAt"] = agreement_accepted_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = d.pop("id", UNSET)

        nickname = d.pop("nickname", UNSET)

        avatar_url = d.pop("avatarUrl", UNSET)

        phone = d.pop("phone", UNSET)

        _plan = d.pop("plan", UNSET)
        plan: UserProfilePlan | Unset
        if isinstance(_plan, Unset):
            plan = UNSET
        else:
            plan = UserProfilePlan(_plan)

        _agreement_accepted_at = d.pop("agreementAcceptedAt", UNSET)
        agreement_accepted_at: datetime.datetime | Unset
        if isinstance(_agreement_accepted_at, Unset):
            agreement_accepted_at = UNSET
        else:
            agreement_accepted_at = datetime.datetime.fromisoformat(_agreement_accepted_at)

        user_profile = cls(
            id=id,
            nickname=nickname,
            avatar_url=avatar_url,
            phone=phone,
            plan=plan,
            agreement_accepted_at=agreement_accepted_at,
        )

        user_profile.additional_properties = d
        return user_profile

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
