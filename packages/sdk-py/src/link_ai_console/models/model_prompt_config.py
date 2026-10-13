from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.model_prompt_config_variables_item import ModelPromptConfigVariablesItem


T = TypeVar("T", bound="ModelPromptConfig")


@_attrs_define
class ModelPromptConfig:
    """
    Attributes:
        model_code (str | Unset): 模型元数据编码（service-api.yaml#/components/schemas/Model.code）
        system_prompt (str | Unset): 应用设定（人设/流程/约束），用户数据
        temperature (float | Unset):
        memory_rounds (int | Unset):
        context_length (int | Unset):
        variables (list[ModelPromptConfigVariablesItem] | Unset):
    """

    model_code: str | Unset = UNSET
    system_prompt: str | Unset = UNSET
    temperature: float | Unset = UNSET
    memory_rounds: int | Unset = UNSET
    context_length: int | Unset = UNSET
    variables: list[ModelPromptConfigVariablesItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        model_code = self.model_code

        system_prompt = self.system_prompt

        temperature = self.temperature

        memory_rounds = self.memory_rounds

        context_length = self.context_length

        variables: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.variables, Unset):
            variables = []
            for variables_item_data in self.variables:
                variables_item = variables_item_data.to_dict()
                variables.append(variables_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if model_code is not UNSET:
            field_dict["modelCode"] = model_code
        if system_prompt is not UNSET:
            field_dict["systemPrompt"] = system_prompt
        if temperature is not UNSET:
            field_dict["temperature"] = temperature
        if memory_rounds is not UNSET:
            field_dict["memoryRounds"] = memory_rounds
        if context_length is not UNSET:
            field_dict["contextLength"] = context_length
        if variables is not UNSET:
            field_dict["variables"] = variables

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.model_prompt_config_variables_item import ModelPromptConfigVariablesItem  # noqa: PLC0415

        d = dict(src_dict)
        model_code = d.pop("modelCode", UNSET)

        system_prompt = d.pop("systemPrompt", UNSET)

        temperature = d.pop("temperature", UNSET)

        memory_rounds = d.pop("memoryRounds", UNSET)

        context_length = d.pop("contextLength", UNSET)

        _variables = d.pop("variables", UNSET)
        variables: list[ModelPromptConfigVariablesItem] | Unset = UNSET
        if _variables is not UNSET:
            variables = []
            for variables_item_data in _variables:
                variables_item = ModelPromptConfigVariablesItem.from_dict(variables_item_data)

                variables.append(variables_item)

        model_prompt_config = cls(
            model_code=model_code,
            system_prompt=system_prompt,
            temperature=temperature,
            memory_rounds=memory_rounds,
            context_length=context_length,
            variables=variables,
        )

        model_prompt_config.additional_properties = d
        return model_prompt_config

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
