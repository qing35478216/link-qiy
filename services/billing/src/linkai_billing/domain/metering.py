"""统一计量的消费侧 DTO——model-proxy `MeteringEvent` 的计费投影。

生产方：`services/model-proxy/domain/metering.py`（只发事件，不含计费规则，
docs/03 §3.4②）。本模块是消费侧的唯一入口形状：
- 字段与生产方 `to_payload()` 一一对应（跨服务/跨语言友好，仅标量）；
- `is_billable` 与生产方语义一致：FAILED 尝试不计费（但仍上报供对账）；
- 计费积分为生产方已折算好的 `credits`（CreditCalculator，ROUND_CEILING
  向上取整不漏计）——billing **不重复折算**，只做原子扣减，避免两套规则漂移。

幂等键：`request_id = event_id`（MQ 重投/HTTP 重试/并发重复投递只扣一次）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class MeteringOutcome(StrEnum):
    """与生产方 MeteringOutcome 同构（字符串值即契约）。"""

    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK_SUCCEEDED = "fallback_succeeded"


@dataclass(frozen=True, slots=True)
class MeteringEventIn:
    """一条待计费的计量事件（不可变；构造即校验）。"""

    event_id: str
    tenant_id: str
    credits: int
    outcome: MeteringOutcome
    provider: str
    model_code: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    attempt: int = 1
    trace_id: str | None = None
    app_code: str | None = None
    conversation_id: str | None = None
    error_code: str | None = None
    fallback_from: str | None = None
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("MeteringEventIn.tenant_id 不能为空（铁律 6 多租户）")
        if not self.event_id:
            raise ValueError("MeteringEventIn.event_id 不能为空（幂等键 = event_id）")
        if not isinstance(self.credits, int) or isinstance(self.credits, bool):
            raise TypeError("credits 必须为整数积分（禁浮点）")
        if self.credits < 0:
            raise ValueError("credits 不能为负（免费模型为 0）")
        if self.attempt < 1:
            raise ValueError("attempt 从 1 起计")

    @property
    def request_id(self) -> str:
        """幂等键——与生产方约定为 event_id。"""
        return self.event_id

    @property
    def is_billable(self) -> bool:
        """失败尝试不计费（与生产方 is_billable 同语义）。"""
        return self.outcome is not MeteringOutcome.FAILED

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> MeteringEventIn:
        """从 MQ/HTTP 载荷构造（生产方 to_payload 的形状）。

        跨服务边界只信标量：字段缺失/类型错误一律显式抛错，
        **禁止**默认值兜底静默吞掉计费字段（漏计即资金事故）。
        """
        occurred_raw = payload.get("occurred_at")
        occurred_at: datetime | None = None
        if occurred_raw is not None:
            if not isinstance(occurred_raw, str):
                raise ValueError("occurred_at 必须为 ISO 字符串")
            occurred_at = datetime.fromisoformat(occurred_raw)
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)

        def _int(name: str, default: int = 0) -> int:
            """取整数字段（双传输兼容）：HTTP JSON 原生 int；Redis Stream
            全字符串（数值以十进制字符串承载）——两者都接受，非数值拒绝。"""
            value = payload.get(name, default)
            if isinstance(value, bool):
                raise ValueError(f"{name} 必须为整数")
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError as exc:
                    raise ValueError(f"{name} 必须为整数") from exc
            raise ValueError(f"{name} 必须为整数")

        def _str(name: str, *, required: bool = False) -> str | None:
            value = payload.get(name)
            if value is None:
                if required:
                    raise ValueError(f"{name} 缺失")
                return None
            if not isinstance(value, str):
                raise ValueError(f"{name} 必须为字符串")
            return value

        outcome_raw = _str("outcome", required=True)
        assert outcome_raw is not None
        return cls(
            event_id=_str("event_id", required=True) or "",
            tenant_id=_str("tenant_id", required=True) or "",
            credits=_int("credits"),
            outcome=MeteringOutcome(outcome_raw),
            provider=_str("provider", required=True) or "",
            model_code=_str("model_code", required=True) or "",
            prompt_tokens=_int("prompt_tokens"),
            completion_tokens=_int("completion_tokens"),
            total_tokens=_int("total_tokens"),
            latency_ms=_int("latency_ms"),
            attempt=_int("attempt", 1),
            trace_id=_str("trace_id"),
            app_code=_str("app_code"),
            conversation_id=_str("conversation_id"),
            error_code=_str("error_code"),
            fallback_from=_str("fallback_from"),
            occurred_at=occurred_at,
        )
