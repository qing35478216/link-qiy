from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="QuotaSummaryUsage")


@_attrs_define
class QuotaSummaryUsage:
    """
    Attributes:
        messages_used (int | Unset):
        messages_limit (int | Unset):
        tokens_used (int | Unset):
        tokens_limit (int | Unset):
    """

    messages_used: int | Unset = UNSET
    messages_limit: int | Unset = UNSET
    tokens_used: int | Unset = UNSET
    tokens_limit: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        messages_used = self.messages_used

        messages_limit = self.messages_limit

        tokens_used = self.tokens_used

        tokens_limit = self.tokens_limit

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if messages_used is not UNSET:
            field_dict["messagesUsed"] = messages_used
        if messages_limit is not UNSET:
            field_dict["messagesLimit"] = messages_limit
        if tokens_used is not UNSET:
            field_dict["tokensUsed"] = tokens_used
        if tokens_limit is not UNSET:
            field_dict["tokensLimit"] = tokens_limit

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        messages_used = d.pop("messagesUsed", UNSET)

        messages_limit = d.pop("messagesLimit", UNSET)

        tokens_used = d.pop("tokensUsed", UNSET)

        tokens_limit = d.pop("tokensLimit", UNSET)

        quota_summary_usage = cls(
            messages_used=messages_used,
            messages_limit=messages_limit,
            tokens_used=tokens_used,
            tokens_limit=tokens_limit,
        )

        quota_summary_usage.additional_properties = d
        return quota_summary_usage

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
