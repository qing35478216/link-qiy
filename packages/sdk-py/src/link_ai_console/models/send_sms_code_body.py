from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.send_sms_code_body_scene import SendSmsCodeBodyScene
from ..types import UNSET, Unset

T = TypeVar("T", bound="SendSmsCodeBody")


@_attrs_define
class SendSmsCodeBody:
    """
    Attributes:
        phone (str):  Example: 13800138000.
        scene (SendSmsCodeBodyScene | Unset):  Default: SendSmsCodeBodyScene.LOGIN.
    """

    phone: str
    scene: SendSmsCodeBodyScene | Unset = SendSmsCodeBodyScene.LOGIN
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        phone = self.phone

        scene: str | Unset = UNSET
        if not isinstance(self.scene, Unset):
            scene = self.scene.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "phone": phone,
            }
        )
        if scene is not UNSET:
            field_dict["scene"] = scene

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        phone = d.pop("phone")

        _scene = d.pop("scene", UNSET)
        scene: SendSmsCodeBodyScene | Unset
        if isinstance(_scene, Unset):
            scene = UNSET
        else:
            scene = SendSmsCodeBodyScene(_scene)

        send_sms_code_body = cls(
            phone=phone,
            scene=scene,
        )

        send_sms_code_body.additional_properties = d
        return send_sms_code_body

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
