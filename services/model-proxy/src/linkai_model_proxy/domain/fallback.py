"""降级链——主模型失败时自动切备选。

设计取舍：平台**不预设**降级顺序（角色定义要求"平台不预设最佳值"），
顺序来自 `ModelCard.fallback_codes`；是否切换由错误是否 `retriable` 决定。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from linkai_model_proxy.domain.errors import DomainError, ModelCallFailure
from linkai_model_proxy.domain.model_card import ModelCard

# 目录解析回调：按模型编码取卡片，取不到返回 None
CatalogResolver = Callable[[str], "ModelCard | None"]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """重试与降级策略。

    - `max_attempts`：单模型内对同一候选的重试次数（含首次），仅对可重试错误生效；
    - `honor_fallback_chain`：主模型耗尽重试后是否切 `fallback_codes` 里的备选；
    - `backoff_base_ms`：指数退避基数（0 表示测试/本地不做等待）。
    """

    max_attempts: int = 1
    honor_fallback_chain: bool = True
    backoff_base_ms: int = 0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts 至少为 1")

    def delay_ms(self, attempt: int) -> int:
        """指数退避时长（毫秒）。attempt 从 1 起。"""
        if self.backoff_base_ms <= 0:
            return 0
        exponent: int = max(0, attempt - 1)
        factor: int = 1 << exponent  # 1<<n == 2**n，避免 mypy 推断为 Any
        return self.backoff_base_ms * factor


@dataclass(frozen=True, slots=True)
class FallbackDecision:
    """一次候选切换决策。

    `index` 是候选链中的序号（1 起），`is_primary` 便于埋点区分首投与降级。
    """

    card: ModelCard
    index: int
    is_primary: bool

    @property
    def attempt_label(self) -> str:
        return "primary" if self.is_primary else f"fallback#{self.index - 1}"


class FallbackPlanner:
    """把主卡片展开成有序候选链。"""

    def __init__(self, *, policy: RetryPolicy | None = None) -> None:
        self.policy = policy or RetryPolicy()

    def plan(self, primary: ModelCard, resolve: CatalogResolver) -> list[FallbackDecision]:
        """构造候选链。

        `resolve` 用于按编码取备选卡片；解析不到的编码静默跳过
        （目录可能滞后于降级配置，不该让整个调用失败）。
        禁用/不可用的备选同样跳过。
        """
        decisions = [FallbackDecision(card=primary, index=1, is_primary=True)]
        if not self.policy.honor_fallback_chain:
            return decisions

        seen = {primary.code}
        for code in primary.fallback_codes:
            if code in seen:
                continue  # 防止配置成环导致无限循环
            seen.add(code)
            card = resolve(code)
            if card is None or not card.enabled:
                continue
            decisions.append(
                FallbackDecision(card=card, index=len(decisions) + 1, is_primary=False)
            )
        return decisions

    @staticmethod
    def should_fallback(error: DomainError) -> bool:
        """该错误是否值得切备选。

        - `ProviderCallError` 子类（超时/5xx/429）→ 可降级；
        - 参数错误/凭证缺失等语义错误 → 不降级（换模型也白搭，直接失败更快）。
        """
        return error.retriable


# 目录解析回调类型别名（避免 ports 与 fallback 循环依赖）


def raise_all_failed(primary_code: str, errors: list[tuple[str, DomainError]]) -> None:
    """候选链全部失败时抛终局错误，保留首个失败原因以便排障。"""
    if not errors:
        raise ModelCallFailure(f"模型 {primary_code} 无可用候选")
    first_model, first_error = errors[0]
    detail = "; ".join(f"{code}: {err}" for code, err in errors)
    raise ModelCallFailure(
        f"模型 {primary_code} 全部候选失败（首个失败于 {first_model}: {first_error}）｜{detail}",
        retriable=False,
    )
