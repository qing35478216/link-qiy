from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="AdvancedConfig")


@_attrs_define
class AdvancedConfig:
    """
    Attributes:
        human_transfer_enabled (bool | Unset):
        human_transfer_keyword (str | Unset):
        humanize_enabled (bool | Unset):
        rate_limit_qpm (int | Unset):
    """

    human_transfer_enabled: bool | Unset = UNSET
    human_transfer_keyword: str | Unset = UNSET
    humanize_enabled: bool | Unset = UNSET
    rate_limit_qpm: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        human_transfer_enabled = self.human_transfer_enabled

        human_transfer_keyword = self.human_transfer_keyword

        humanize_enabled = self.humanize_enabled

        rate_limit_qpm = self.rate_limit_qpm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if human_transfer_enabled is not UNSET:
            field_dict["humanTransferEnabled"] = human_transfer_enabled
        if human_transfer_keyword is not UNSET:
            field_dict["humanTransferKeyword"] = human_transfer_keyword
        if humanize_enabled is not UNSET:
            field_dict["humanizeEnabled"] = humanize_enabled
        if rate_limit_qpm is not UNSET:
            field_dict["rateLimitQpm"] = rate_limit_qpm

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        human_transfer_enabled = d.pop("humanTransferEnabled", UNSET)

        human_transfer_keyword = d.pop("humanTransferKeyword", UNSET)

        humanize_enabled = d.pop("humanizeEnabled", UNSET)

        rate_limit_qpm = d.pop("rateLimitQpm", UNSET)

        advanced_config = cls(
            human_transfer_enabled=human_transfer_enabled,
            human_transfer_keyword=human_transfer_keyword,
            humanize_enabled=humanize_enabled,
            rate_limit_qpm=rate_limit_qpm,
        )

        advanced_config.additional_properties = d
        return advanced_config

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
