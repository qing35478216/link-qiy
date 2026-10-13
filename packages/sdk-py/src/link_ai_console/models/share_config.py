from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ShareConfig")


@_attrs_define
class ShareConfig:
    """
    Attributes:
        share_enabled (bool | Unset):
        share_path (str | Unset):
        show_branding (bool | Unset):
    """

    share_enabled: bool | Unset = UNSET
    share_path: str | Unset = UNSET
    show_branding: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        share_enabled = self.share_enabled

        share_path = self.share_path

        show_branding = self.show_branding

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if share_enabled is not UNSET:
            field_dict["shareEnabled"] = share_enabled
        if share_path is not UNSET:
            field_dict["sharePath"] = share_path
        if show_branding is not UNSET:
            field_dict["showBranding"] = show_branding

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        share_enabled = d.pop("shareEnabled", UNSET)

        share_path = d.pop("sharePath", UNSET)

        show_branding = d.pop("showBranding", UNSET)

        share_config = cls(
            share_enabled=share_enabled,
            share_path=share_path,
            show_branding=show_branding,
        )

        share_config.additional_properties = d
        return share_config

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
