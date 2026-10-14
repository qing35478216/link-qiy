from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.create_wechat_qrcode_body_scene import CreateWechatQrcodeBodyScene
from ..types import UNSET, Unset

T = TypeVar("T", bound="CreateWechatQrcodeBody")


@_attrs_define
class CreateWechatQrcodeBody:
    """
    Attributes:
        agreement_accepted (bool):
        scene (CreateWechatQrcodeBodyScene | Unset):  Default: CreateWechatQrcodeBodyScene.LOGIN.
    """

    agreement_accepted: bool
    scene: CreateWechatQrcodeBodyScene | Unset = CreateWechatQrcodeBodyScene.LOGIN
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        agreement_accepted = self.agreement_accepted

        scene: str | Unset = UNSET
        if not isinstance(self.scene, Unset):
            scene = self.scene.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "agreementAccepted": agreement_accepted,
            }
        )
        if scene is not UNSET:
            field_dict["scene"] = scene

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        agreement_accepted = d.pop("agreementAccepted")

        _scene = d.pop("scene", UNSET)
        scene: CreateWechatQrcodeBodyScene | Unset
        if isinstance(_scene, Unset):
            scene = UNSET
        else:
            scene = CreateWechatQrcodeBodyScene(_scene)

        create_wechat_qrcode_body = cls(
            agreement_accepted=agreement_accepted,
            scene=scene,
        )

        create_wechat_qrcode_body.additional_properties = d
        return create_wechat_qrcode_body

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
