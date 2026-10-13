from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.get_wechat_qrcode_status_response_200_status import GetWechatQrcodeStatusResponse200Status
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.token_pair import TokenPair


T = TypeVar("T", bound="GetWechatQrcodeStatusResponse200")


@_attrs_define
class GetWechatQrcodeStatusResponse200:
    """
    Attributes:
        status (GetWechatQrcodeStatusResponse200Status):
        tokens (TokenPair | Unset):
    """

    status: GetWechatQrcodeStatusResponse200Status
    tokens: TokenPair | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        status = self.status.value

        tokens: dict[str, Any] | Unset = UNSET
        if not isinstance(self.tokens, Unset):
            tokens = self.tokens.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
            }
        )
        if tokens is not UNSET:
            field_dict["tokens"] = tokens

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.token_pair import TokenPair  # noqa: PLC0415

        d = dict(src_dict)
        status = GetWechatQrcodeStatusResponse200Status(d.pop("status"))

        _tokens = d.pop("tokens", UNSET)
        tokens: TokenPair | Unset
        if isinstance(_tokens, Unset):
            tokens = UNSET
        else:
            tokens = TokenPair.from_dict(_tokens)

        get_wechat_qrcode_status_response_200 = cls(
            status=status,
            tokens=tokens,
        )

        get_wechat_qrcode_status_response_200.additional_properties = d
        return get_wechat_qrcode_status_response_200

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
