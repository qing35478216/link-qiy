from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.plugins_config_exec_strategy import PluginsConfigExecStrategy
from ..types import UNSET, Unset

T = TypeVar("T", bound="PluginsConfig")


@_attrs_define
class PluginsConfig:
    """
    Attributes:
        plugin_ids (list[str] | Unset):
        exec_strategy (PluginsConfigExecStrategy | Unset):
        trigger_keywords (list[str] | Unset):
    """

    plugin_ids: list[str] | Unset = UNSET
    exec_strategy: PluginsConfigExecStrategy | Unset = UNSET
    trigger_keywords: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plugin_ids: list[str] | Unset = UNSET
        if not isinstance(self.plugin_ids, Unset):
            plugin_ids = self.plugin_ids

        exec_strategy: str | Unset = UNSET
        if not isinstance(self.exec_strategy, Unset):
            exec_strategy = self.exec_strategy.value

        trigger_keywords: list[str] | Unset = UNSET
        if not isinstance(self.trigger_keywords, Unset):
            trigger_keywords = self.trigger_keywords

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if plugin_ids is not UNSET:
            field_dict["pluginIds"] = plugin_ids
        if exec_strategy is not UNSET:
            field_dict["execStrategy"] = exec_strategy
        if trigger_keywords is not UNSET:
            field_dict["triggerKeywords"] = trigger_keywords

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        plugin_ids = cast(list[str], d.pop("pluginIds", UNSET))

        _exec_strategy = d.pop("execStrategy", UNSET)
        exec_strategy: PluginsConfigExecStrategy | Unset
        if isinstance(_exec_strategy, Unset):
            exec_strategy = UNSET
        else:
            exec_strategy = PluginsConfigExecStrategy(_exec_strategy)

        trigger_keywords = cast(list[str], d.pop("triggerKeywords", UNSET))

        plugins_config = cls(
            plugin_ids=plugin_ids,
            exec_strategy=exec_strategy,
            trigger_keywords=trigger_keywords,
        )

        plugins_config.additional_properties = d
        return plugins_config

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
