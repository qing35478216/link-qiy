"""出站端口——领域层定义的接口，由 infra 层实现（依赖只准向内，铁律 2）。

这些 `Protocol` 是 domain 与外部世界（DB / MQ / 网络）之间唯一的接缝。
"""

from __future__ import annotations

from typing import Protocol

from linkai_model_proxy.domain.adapter import ProviderCredential
from linkai_model_proxy.domain.invocation import ChatRequest
from linkai_model_proxy.domain.metering import MeteringEvent
from linkai_model_proxy.domain.model_card import ModelCard, ModelCatalogSnapshot


class ModelCatalog(Protocol):
    """模型目录端口。

    实现方负责多租户过滤（铁律 6）：每个方法签名都必须能承载 tenant_id，
    实现里禁止裸查询。Phase 0 用内存实现，Phase 1 换DB 不改业务代码。
    """

    def snapshot(self, tenant_id: str) -> ModelCatalogSnapshot:
        """取某租户可见的模型目录快照（平台公共模型 + 该租户自建模型）。"""
        ...

    def find(self, tenant_id: str, code: str) -> ModelCard | None:
        """按编码取单个模型卡片，不存在返回 None。"""
        ...


class CredentialResolver(Protocol):
    """凭证解析端口。

    实现顺序约定：先查用户自带 Key（自定义模型），再回落到平台 Key。
    实现方**必须**保证返回的 `secret` 不落日志。
    """

    async def resolve(
        self,
        tenant_id: str,
        card: ModelCard,
        *,
        request: ChatRequest,
    ) -> ProviderCredential | None:
        """解析可用的厂商凭证；无可用凭证返回 None（由上层抛错）。"""
        ...


class TelemetrySink(Protocol):
    """遥测出口——承载 MeteringEvent（docs/03 §3.4② 统一计量）。

    Phase 0：进程内实现（测试与本地）；Phase 1：MQ 实现（billing 原子扣减）。
    两种实现都满足"入口只发事件，不感知计费规则"。
    """

    async def emit_metering(self, event: MeteringEvent) -> None: ...


class TokenEstimator(Protocol):
    """token 估算器——厂商未返回 usage 时的兜底，保证计量永不缺数。"""

    def estimate(self, request: ChatRequest, response_text: str) -> tuple[int, int]:
        """返回 `(prompt_tokens, completion_tokens)` 估算值。"""
        ...
