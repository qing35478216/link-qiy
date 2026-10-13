from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.advanced_config import AdvancedConfig
    from ..models.basic_config import BasicConfig
    from ..models.data_config import DataConfig
    from ..models.knowledge_config import KnowledgeConfig
    from ..models.model_prompt_config import ModelPromptConfig
    from ..models.plugins_config import PluginsConfig
    from ..models.share_config import ShareConfig


T = TypeVar("T", bound="AppConfig")


@_attrs_define
class AppConfig:
    """配置七件套——全部段落透传至运行时（平台不预设最佳值）

    Attributes:
        basic (BasicConfig | Unset):
        share (ShareConfig | Unset):
        model_prompt (ModelPromptConfig | Unset):
        knowledge (KnowledgeConfig | Unset):
        data (DataConfig | Unset):
        plugins (PluginsConfig | Unset):
        advanced (AdvancedConfig | Unset):
    """

    basic: BasicConfig | Unset = UNSET
    share: ShareConfig | Unset = UNSET
    model_prompt: ModelPromptConfig | Unset = UNSET
    knowledge: KnowledgeConfig | Unset = UNSET
    data: DataConfig | Unset = UNSET
    plugins: PluginsConfig | Unset = UNSET
    advanced: AdvancedConfig | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        basic: dict[str, Any] | Unset = UNSET
        if not isinstance(self.basic, Unset):
            basic = self.basic.to_dict()

        share: dict[str, Any] | Unset = UNSET
        if not isinstance(self.share, Unset):
            share = self.share.to_dict()

        model_prompt: dict[str, Any] | Unset = UNSET
        if not isinstance(self.model_prompt, Unset):
            model_prompt = self.model_prompt.to_dict()

        knowledge: dict[str, Any] | Unset = UNSET
        if not isinstance(self.knowledge, Unset):
            knowledge = self.knowledge.to_dict()

        data: dict[str, Any] | Unset = UNSET
        if not isinstance(self.data, Unset):
            data = self.data.to_dict()

        plugins: dict[str, Any] | Unset = UNSET
        if not isinstance(self.plugins, Unset):
            plugins = self.plugins.to_dict()

        advanced: dict[str, Any] | Unset = UNSET
        if not isinstance(self.advanced, Unset):
            advanced = self.advanced.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if basic is not UNSET:
            field_dict["basic"] = basic
        if share is not UNSET:
            field_dict["share"] = share
        if model_prompt is not UNSET:
            field_dict["modelPrompt"] = model_prompt
        if knowledge is not UNSET:
            field_dict["knowledge"] = knowledge
        if data is not UNSET:
            field_dict["data"] = data
        if plugins is not UNSET:
            field_dict["plugins"] = plugins
        if advanced is not UNSET:
            field_dict["advanced"] = advanced

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.advanced_config import AdvancedConfig  # noqa: PLC0415
        from ..models.basic_config import BasicConfig  # noqa: PLC0415
        from ..models.data_config import DataConfig  # noqa: PLC0415
        from ..models.knowledge_config import KnowledgeConfig  # noqa: PLC0415
        from ..models.model_prompt_config import ModelPromptConfig  # noqa: PLC0415
        from ..models.plugins_config import PluginsConfig  # noqa: PLC0415
        from ..models.share_config import ShareConfig  # noqa: PLC0415

        d = dict(src_dict)
        _basic = d.pop("basic", UNSET)
        basic: BasicConfig | Unset
        if isinstance(_basic, Unset):
            basic = UNSET
        else:
            basic = BasicConfig.from_dict(_basic)

        _share = d.pop("share", UNSET)
        share: ShareConfig | Unset
        if isinstance(_share, Unset):
            share = UNSET
        else:
            share = ShareConfig.from_dict(_share)

        _model_prompt = d.pop("modelPrompt", UNSET)
        model_prompt: ModelPromptConfig | Unset
        if isinstance(_model_prompt, Unset):
            model_prompt = UNSET
        else:
            model_prompt = ModelPromptConfig.from_dict(_model_prompt)

        _knowledge = d.pop("knowledge", UNSET)
        knowledge: KnowledgeConfig | Unset
        if isinstance(_knowledge, Unset):
            knowledge = UNSET
        else:
            knowledge = KnowledgeConfig.from_dict(_knowledge)

        _data = d.pop("data", UNSET)
        data: DataConfig | Unset
        if isinstance(_data, Unset):
            data = UNSET
        else:
            data = DataConfig.from_dict(_data)

        _plugins = d.pop("plugins", UNSET)
        plugins: PluginsConfig | Unset
        if isinstance(_plugins, Unset):
            plugins = UNSET
        else:
            plugins = PluginsConfig.from_dict(_plugins)

        _advanced = d.pop("advanced", UNSET)
        advanced: AdvancedConfig | Unset
        if isinstance(_advanced, Unset):
            advanced = UNSET
        else:
            advanced = AdvancedConfig.from_dict(_advanced)

        app_config = cls(
            basic=basic,
            share=share,
            model_prompt=model_prompt,
            knowledge=knowledge,
            data=data,
            plugins=plugins,
            advanced=advanced,
        )

        app_config.additional_properties = d
        return app_config

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
