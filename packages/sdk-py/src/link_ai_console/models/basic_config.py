from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="BasicConfig")


@_attrs_define
class BasicConfig:
    """
    Attributes:
        welcome_message (str | Unset):
        guide_questions (list[str] | Unset):
        avatar_url (str | Unset):
    """

    welcome_message: str | Unset = UNSET
    guide_questions: list[str] | Unset = UNSET
    avatar_url: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        welcome_message = self.welcome_message

        guide_questions: list[str] | Unset = UNSET
        if not isinstance(self.guide_questions, Unset):
            guide_questions = self.guide_questions

        avatar_url = self.avatar_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if welcome_message is not UNSET:
            field_dict["welcomeMessage"] = welcome_message
        if guide_questions is not UNSET:
            field_dict["guideQuestions"] = guide_questions
        if avatar_url is not UNSET:
            field_dict["avatarUrl"] = avatar_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        welcome_message = d.pop("welcomeMessage", UNSET)

        guide_questions = cast(list[str], d.pop("guideQuestions", UNSET))

        avatar_url = d.pop("avatarUrl", UNSET)

        basic_config = cls(
            welcome_message=welcome_message,
            guide_questions=guide_questions,
            avatar_url=avatar_url,
        )

        basic_config.additional_properties = d
        return basic_config

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
