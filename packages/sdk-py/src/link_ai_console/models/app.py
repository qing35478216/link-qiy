from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.app_type import AppType
from ..types import UNSET, Unset

T = TypeVar("T", bound="App")


@_attrs_define
class App:
    """
    Attributes:
        name (str):
        type_ (AppType):
        id (str | Unset):
        description (str | Unset):
        icon_url (str | Unset):
        published (bool | Unset):
        current_version (int | Unset):
        created_at (datetime.datetime | Unset):
        updated_at (datetime.datetime | Unset):
    """

    name: str
    type_: AppType
    id: str | Unset = UNSET
    description: str | Unset = UNSET
    icon_url: str | Unset = UNSET
    published: bool | Unset = UNSET
    current_version: int | Unset = UNSET
    created_at: datetime.datetime | Unset = UNSET
    updated_at: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        type_ = self.type_.value

        id = self.id

        description = self.description

        icon_url = self.icon_url

        published = self.published

        current_version = self.current_version

        created_at: str | Unset = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        updated_at: str | Unset = UNSET
        if not isinstance(self.updated_at, Unset):
            updated_at = self.updated_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "type": type_,
            }
        )
        if id is not UNSET:
            field_dict["id"] = id
        if description is not UNSET:
            field_dict["description"] = description
        if icon_url is not UNSET:
            field_dict["iconUrl"] = icon_url
        if published is not UNSET:
            field_dict["published"] = published
        if current_version is not UNSET:
            field_dict["currentVersion"] = current_version
        if created_at is not UNSET:
            field_dict["createdAt"] = created_at
        if updated_at is not UNSET:
            field_dict["updatedAt"] = updated_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        type_ = AppType(d.pop("type"))

        id = d.pop("id", UNSET)

        description = d.pop("description", UNSET)

        icon_url = d.pop("iconUrl", UNSET)

        published = d.pop("published", UNSET)

        current_version = d.pop("currentVersion", UNSET)

        _created_at = d.pop("createdAt", UNSET)
        created_at: datetime.datetime | Unset
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = datetime.datetime.fromisoformat(_created_at)

        _updated_at = d.pop("updatedAt", UNSET)
        updated_at: datetime.datetime | Unset
        if isinstance(_updated_at, Unset):
            updated_at = UNSET
        else:
            updated_at = datetime.datetime.fromisoformat(_updated_at)

        app = cls(
            name=name,
            type_=type_,
            id=id,
            description=description,
            icon_url=icon_url,
            published=published,
            current_version=current_version,
            created_at=created_at,
            updated_at=updated_at,
        )

        app.additional_properties = d
        return app

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
