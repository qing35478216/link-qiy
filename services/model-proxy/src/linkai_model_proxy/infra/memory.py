"""infra 层端口实现——内存版本（Phase 0）。

三件套都按domain 的 `Protocol` 编程，Phase 1 换 Redis / MQ / PostgreSQL
**不改业务代码**（铁律 4 的另一个落点）。

⚠️ 安全：`InMemoryCredentialStore` 存明文凭证仅限本地开发。
生产必须换成 KMS / Vault 或 DB 加密列——该替换是 infra 内部改动。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from linkai_model_proxy.domain.adapter import ProviderCredential
from linkai_model_proxy.domain.invocation import ChatRequest
from linkai_model_proxy.domain.metering import MeteringEvent
from linkai_model_proxy.domain.model_card import ModelCard, ModelCatalogSnapshot
from linkai_model_proxy.domain.ports import (
    CredentialResolver,
    ModelCatalog,
    TelemetrySink,
    TokenEstimator,
)


class InMemoryModelCatalog(ModelCatalog):
    """内存模型目录。

    多租户（铁律 6）：公共模型对所有租户可见；租户私有模型只对该租户可见。
    查询一律以 `tenant_id` 为第一入参——没有"裸查询"的方法签名。
    """

    def __init__(
        self,
        *,
        public_models: dict[str, ModelCard] | None = None,
        tenant_models: dict[str, dict[str, ModelCard]] | None = None,
    ) -> None:
        self._public = dict(public_models or {})
        self._tenant = {t: dict(m) for t, m in (tenant_models or {}).items()}

    def snapshot(self, tenant_id: str) -> ModelCatalogSnapshot:
        merged: dict[str, ModelCard] = dict(self._public)
        # 租户私有模型覆盖同名公共模型（用户自带 Key 的自定义模型）
        merged.update(self._tenant.get(tenant_id, {}))
        return ModelCatalogSnapshot.of(merged)

    def find(self, tenant_id: str, code: str) -> ModelCard | None:
        return self._tenant.get(tenant_id, {}).get(code) or self._public.get(code)

    def add_tenant_model(self, tenant_id: str, card: ModelCard) -> None:
        """登记租户自定义模型（自定义模型场景）。"""
        self._tenant.setdefault(tenant_id, {})[card.code] = card


@dataclass(slots=True)
class InMemoryCredentialStore(CredentialResolver):
    """凭证解析：先租户自带 Key（byok），再回落平台 Key。

    `platform_keys` 是 `{provider: secret}`，`tenant_keys` 是
    `{(tenant_id, provider): secret}`。生产应换成加密存储。
    """

    platform_keys: dict[str, str] = field(default_factory=dict)
    tenant_keys: dict[tuple[str, str], str] = field(default_factory=dict)
    base_urls: dict[str, str] = field(default_factory=dict)

    async def resolve(
        self,
        tenant_id: str,
        card: ModelCard,
        *,
        request: ChatRequest,
    ) -> ProviderCredential | None:
        # 1) 租户自带 Key 优先（自定义模型花钱走用户自己的账）
        secret = self.tenant_keys.get((tenant_id, card.provider))
        # 2) 回落平台公共 Key
        if not secret:
            secret = self.platform_keys.get(card.provider)
        if not secret:
            return None
        return ProviderCredential(
            provider=card.provider,
            secret=secret,
            base_url=self.base_urls.get(card.provider),
        )


class InMemoryTelemetrySink(TelemetrySink):
    """进程内计量事件收集器（Phase 0）。

    同时充当测试断言的抓取点——`assert_one_event(...)`。
    Phase 1 换成 MQ 发布（billing 原子扣减）。
    """

    def __init__(self) -> None:
        self.events: list[MeteringEvent] = []

    async def emit_metering(self, event: MeteringEvent) -> None:
        self.events.append(event)

    # ---------- 测试辅助 ----------

    def last(self) -> MeteringEvent | None:
        return self.events[-1] if self.events else None

    def for_model(self, code: str) -> list[MeteringEvent]:
        return [e for e in self.events if e.model_code == code]

    def for_tenant(self, tenant_id: str) -> list[MeteringEvent]:
        return [e for e in self.events if e.tenant_id == tenant_id]

    def by_outcome(self, outcome: str) -> list[MeteringEvent]:
        return [e for e in self.events if str(e.outcome) == outcome]

    def total_credits(self, tenant_id: str | None = None) -> int:
        events = self.events if tenant_id is None else self.for_tenant(tenant_id)
        return sum(e.credits for e in events)


class HeuristicTokenEstimator(TokenEstimator):
    """token 启发式估算器——厂商不回usage 时的兜底，保证计量不缺数。

    采用业界通用的"字符数/4"近似，并对 CJK 按"每字≈1 token"加权
    （中文按 4 字符/token 估算会严重低估）。
    这只是兜底：**真实计量以厂商返回的 usage 为准**。
    """

    def __init__(self, *, chars_per_token: float = 4.0, cjk_tokens_per_char: float = 1.0) -> None:
        self._chars_per_token = chars_per_token
        self._cjk_per_char = cjk_tokens_per_char

    def estimate(self, request: ChatRequest, response_text: str) -> tuple[int, int]:
        prompt_tokens = sum(
            self._count(m.role) + self._count_text(m.content) for m in request.messages
        )
        completion_tokens = self._count_text(response_text)
        return max(1, prompt_tokens), max(1, completion_tokens)

    def _count_text(self, text: str) -> int:
        if not text:
            return 0
        cjk = sum(1 for ch in text if self._is_cjk(ch))
        other = len(text) - cjk
        return math.ceil(cjk * self._cjk_per_char + other / self._chars_per_token)

    def _count(self, role: object) -> int:
        # 每条消息的 role/分隔符开销，约 4 token
        return 4

    @staticmethod
    def _is_cjk(ch: str) -> bool:
        code = ord(ch)
        return (
            0x4E00 <= code <= 0x9FFF  # CJK 统一表意
            or 0x3400 <= code <= 0x4DBF  # 扩展 A
            or 0x3000 <= code <= 0x303F  # CJK 标点
            or 0xFF00 <= code <= 0xFFEF  # 全角
        )


class CountingTelemetrySink(InMemoryTelemetrySink):
    """带租户维度的计数视图（便于断言"每个租户独立计量"）。"""

    @property
    def per_tenant_count(self) -> dict[str, int]:
        counter: dict[str, int] = defaultdict(int)
        for event in self.events:
            counter[event.tenant_id] += 1
        return dict(counter)
