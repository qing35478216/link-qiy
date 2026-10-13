from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="DataConfig")


@_attrs_define
class DataConfig:
    """
    Attributes:
        db_dataset_id (str | Unset): 绑定数据库模块数据集
        table_sync_cron (str | Unset): cron 表达式
    """

    db_dataset_id: str | Unset = UNSET
    table_sync_cron: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        db_dataset_id = self.db_dataset_id

        table_sync_cron = self.table_sync_cron

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if db_dataset_id is not UNSET:
            field_dict["dbDatasetId"] = db_dataset_id
        if table_sync_cron is not UNSET:
            field_dict["tableSyncCron"] = table_sync_cron

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        db_dataset_id = d.pop("dbDatasetId", UNSET)

        table_sync_cron = d.pop("tableSyncCron", UNSET)

        data_config = cls(
            db_dataset_id=db_dataset_id,
            table_sync_cron=table_sync_cron,
        )

        data_config.additional_properties = d
        return data_config

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
