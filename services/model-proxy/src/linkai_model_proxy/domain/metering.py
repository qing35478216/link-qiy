"""计量埋点——每次模型调用产出一个 `MeteringEvent`。

契约依据：`packages/contracts/openapi/service-api.yaml#/ChatCompletionResponse.usage`
（promptTokens / completionTokens / totalTokens / credits）与
`runtime-events.yaml#/DoneEvent.data.usage`（同名字段）。
跨服务投递由 T-007 积分钱包消费；本服务**只发事件，不含计费规则**（docs/03 §3.4②）。

铁律：角色定义"不准绕过计量直接调模型"。工程上通过两点保证——
① `ModelInvocationService` 是唯一能拿到 `AdapterRegistry` 的地方；
② 领域服务在成功与失败两条路径上都发事件（失败也计`MeteringOutcome.FAILED`）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from linkai_model_proxy.domain.invocation import TokenUsage
from linkai_model_proxy.domain.model_card import ModelCard, ModelPrice


class MeteringOutcome(StrEnum):
    """调用结局——决定下游是否计费。"""

    SUCCESS = "success"
    FAILED = "failed"
    # 主模型失败、切备选成功：下游按备选模型的真实 token 计费，
    # 失败的那次通常不计费（但仍上报以便对账与厂商成本核算）
    FALLBACK_SUCCEEDED = "fallback_succeeded"


@dataclass(frozen=True, slots=True)
class MeteringEvent:
    """计量事件。

    多租户强约束（铁律 6）：`tenant_id` 必填，且校验非空——
    没有租户的用量无法归属钱包，属于计费事故。
    """

    event_id: str
    tenant_id: str
    app_code: str | None
    conversation_id: str | None
    trace_id: str
    provider: str
    model_code: str
    outcome: MeteringOutcome
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    credits: int
    latency_ms: int
    attempt: int
    occurred_at: datetime
    error_code: str | None = None
    # 降级链信息：若本次是切备选后的成功，记录原始主模型
    fallback_from: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("MeteringEvent.tenant_id 不能为空（铁律 6 多租户）")
        if self.attempt < 1:
            raise ValueError("attempt 从 1 起计")

    @property
    def is_billable(self) -> bool:
        """是否应向用户侧计费——失败尝试不计费。"""
        return self.outcome is not MeteringOutcome.FAILED

    def to_payload(self) -> dict[str, object]:
        """投递给 MQ 的载荷。

        只含标量与字符串，跨语言友好（Go billing / Python 对账都能消费）。
        显式带 `tenant_id`前缀便于 Redis/MQ 侧按租户分区。
        """
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "app_code": self.app_code,
            "conversation_id": self.conversation_id,
            "trace_id": self.trace_id,
            "provider": self.provider,
            "model_code": self.model_code,
            "outcome": str(self.outcome),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "credits": self.credits,
            "latency_ms": self.latency_ms,
            "attempt": self.attempt,
            "occurred_at": self.occurred_at.isoformat(),
            "error_code": self.error_code,
            "fallback_from": self.fallback_from,
        }


class CreditCalculator:
    """积分折算器。

    规则（`ModelPrice`）：
      `credits = ceil(prompt_tokens/1000 * input_per_1k
                      + completion_tokens/1000 * output_per_1k) + credit_per_call`

    用 `Decimal` 避免浮点误差导致的账单抖动；`ROUND_HALF_UP` 与多数厂商计费一致。
    平台**不内置**"最佳定价"——价格来自模型目录，平台只做算术。
    """

    #: 每次调用至少消耗 0 积分（免费模型可以是 0）
    MIN_CREDITS: int = 0

    def __init__(self, *, scale: Decimal = Decimal("0.000001")) -> None:
        # 保留 6 位小数后再 ceiling，抵消 Decimal 乘法的余数噪声
        self._scale = scale

    def compute(self, price: ModelPrice, usage: TokenUsage) -> int:
        """按价格与用量折算积分（向上取整）。"""
        prompt = Decimal(usage.prompt_tokens) / Decimal(1000)
        completion = Decimal(usage.completion_tokens) / Decimal(1000)
        raw = prompt * Decimal(str(price.input_per_1k)) + completion * Decimal(
            str(price.output_per_1k)
        )
        total = raw + Decimal(price.credit_per_call)
        quantized = total.quantize(self._scale, rounding=ROUND_HALF_UP)
        credits = int(quantized.to_integral_value(rounding="ROUND_CEILING"))
        return max(credits, self.MIN_CREDITS)

    def with_credits(self, price: ModelPrice, usage: TokenUsage) -> TokenUsage:
        """回填 credits 字段，产出新的 `TokenUsage`（不可变，安全）。"""
        credits = self.compute(price, usage)
        if usage.credits == credits:
            return usage
        return TokenUsage(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            credits=credits,
        )


def now_utc() -> datetime:
    """当前 UTC 时间——单独抽出便于测试打桩。"""
    return datetime.now(UTC)


def build_event(
    *,
    tenant_id: str,
    provider: str,
    card: ModelCard,
    usage: TokenUsage,
    outcome: MeteringOutcome,
    latency_ms: int,
    attempt: int,
    trace_id: str,
    event_id: str,
    app_code: str | None = None,
    conversation_id: str | None = None,
    error_code: str | None = None,
    fallback_from: str | None = None,
    occurred_at: datetime | None = None,
) -> MeteringEvent:
    """构造计量事件的单一入口——强制必填字段，避免各处散落拼装漏字段。"""
    return MeteringEvent(
        event_id=event_id,
        tenant_id=tenant_id,
        app_code=app_code,
        conversation_id=conversation_id,
        trace_id=trace_id,
        provider=provider,
        model_code=card.code,
        outcome=outcome,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        credits=usage.credits if outcome is not MeteringOutcome.FAILED else 0,
        latency_ms=latency_ms,
        attempt=attempt,
        occurred_at=occurred_at or now_utc(),
        error_code=error_code,
        fallback_from=fallback_from,
    )
