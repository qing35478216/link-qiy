from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="LoginByPhoneBody")


@_attrs_define
class LoginByPhoneBody:
    """
    Attributes:
        phone (str):
        sms_code (str):
        agreement_accepted (bool):
    """

    phone: str
    sms_code: str
    agreement_accepted: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        phone = self.phone

        sms_code = self.sms_code

        agreement_accepted = self.agreement_accepted

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "phone": phone,
                "smsCode": sms_code,
                "agreementAccepted": agreement_accepted,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        phone = d.pop("phone")

        sms_code = d.pop("smsCode")

        agreement_accepted = d.pop("agreementAccepted")

        login_by_phone_body = cls(
            phone=phone,
            sms_code=sms_code,
            agreement_accepted=agreement_accepted,
        )

        login_by_phone_body.additional_properties = d
        return login_by_phone_body

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
