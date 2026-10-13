from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.knowledge_config_miss_strategy import KnowledgeConfigMissStrategy
from ..types import UNSET, Unset

T = TypeVar("T", bound="KnowledgeConfig")


@_attrs_define
class KnowledgeConfig:
    """
    Attributes:
        dataset_ids (list[str] | Unset):
        similarity_threshold (float | Unset):
        semantic_top_k (int | Unset):
        fulltext_top_k (int | Unset):
        miss_strategy (KnowledgeConfigMissStrategy | Unset):
        miss_message (str | Unset):
        citation_enabled (bool | Unset):
        query_rewrite_enabled (bool | Unset):
        rerank_enabled (bool | Unset):
    """

    dataset_ids: list[str] | Unset = UNSET
    similarity_threshold: float | Unset = UNSET
    semantic_top_k: int | Unset = UNSET
    fulltext_top_k: int | Unset = UNSET
    miss_strategy: KnowledgeConfigMissStrategy | Unset = UNSET
    miss_message: str | Unset = UNSET
    citation_enabled: bool | Unset = UNSET
    query_rewrite_enabled: bool | Unset = UNSET
    rerank_enabled: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dataset_ids: list[str] | Unset = UNSET
        if not isinstance(self.dataset_ids, Unset):
            dataset_ids = self.dataset_ids

        similarity_threshold = self.similarity_threshold

        semantic_top_k = self.semantic_top_k

        fulltext_top_k = self.fulltext_top_k

        miss_strategy: str | Unset = UNSET
        if not isinstance(self.miss_strategy, Unset):
            miss_strategy = self.miss_strategy.value

        miss_message = self.miss_message

        citation_enabled = self.citation_enabled

        query_rewrite_enabled = self.query_rewrite_enabled

        rerank_enabled = self.rerank_enabled

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if dataset_ids is not UNSET:
            field_dict["datasetIds"] = dataset_ids
        if similarity_threshold is not UNSET:
            field_dict["similarityThreshold"] = similarity_threshold
        if semantic_top_k is not UNSET:
            field_dict["semanticTopK"] = semantic_top_k
        if fulltext_top_k is not UNSET:
            field_dict["fulltextTopK"] = fulltext_top_k
        if miss_strategy is not UNSET:
            field_dict["missStrategy"] = miss_strategy
        if miss_message is not UNSET:
            field_dict["missMessage"] = miss_message
        if citation_enabled is not UNSET:
            field_dict["citationEnabled"] = citation_enabled
        if query_rewrite_enabled is not UNSET:
            field_dict["queryRewriteEnabled"] = query_rewrite_enabled
        if rerank_enabled is not UNSET:
            field_dict["rerankEnabled"] = rerank_enabled

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dataset_ids = cast(list[str], d.pop("datasetIds", UNSET))

        similarity_threshold = d.pop("similarityThreshold", UNSET)

        semantic_top_k = d.pop("semanticTopK", UNSET)

        fulltext_top_k = d.pop("fulltextTopK", UNSET)

        _miss_strategy = d.pop("missStrategy", UNSET)
        miss_strategy: KnowledgeConfigMissStrategy | Unset
        if isinstance(_miss_strategy, Unset):
            miss_strategy = UNSET
        else:
            miss_strategy = KnowledgeConfigMissStrategy(_miss_strategy)

        miss_message = d.pop("missMessage", UNSET)

        citation_enabled = d.pop("citationEnabled", UNSET)

        query_rewrite_enabled = d.pop("queryRewriteEnabled", UNSET)

        rerank_enabled = d.pop("rerankEnabled", UNSET)

        knowledge_config = cls(
            dataset_ids=dataset_ids,
            similarity_threshold=similarity_threshold,
            semantic_top_k=semantic_top_k,
            fulltext_top_k=fulltext_top_k,
            miss_strategy=miss_strategy,
            miss_message=miss_message,
            citation_enabled=citation_enabled,
            query_rewrite_enabled=query_rewrite_enabled,
            rerank_enabled=rerank_enabled,
        )

        knowledge_config.additional_properties = d
        return knowledge_config

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
