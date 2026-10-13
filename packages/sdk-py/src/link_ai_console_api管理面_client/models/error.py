from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.error_details import ErrorDetails


T = TypeVar("T", bound="Error")


@_attrs_define
class Error:
    """
    Attributes:
        code (str):  Example: AGREEMENT_NOT_ACCEPTED.
        message (str):
        request_id (str): 链路追踪 ID（排障用）
        details (ErrorDetails | Unset):
    """

    code: str
    message: str
    request_id: str
    details: ErrorDetails | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        message = self.message

        request_id = self.request_id

        details: dict[str, Any] | Unset = UNSET
        if not isinstance(self.details, Unset):
            details = self.details.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "message": message,
                "requestId": request_id,
            }
        )
        if details is not UNSET:
            field_dict["details"] = details

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.error_details import ErrorDetails  # noqa: PLC0415

        d = dict(src_dict)
        code = d.pop("code")

        message = d.pop("message")

        request_id = d.pop("requestId")

        _details = d.pop("details", UNSET)
        details: ErrorDetails | Unset
        if isinstance(_details, Unset):
            details = UNSET
        else:
            details = ErrorDetails.from_dict(_details)

        error = cls(
            code=code,
            message=message,
            request_id=request_id,
            details=details,
        )

        error.additional_properties = d
        return error

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
