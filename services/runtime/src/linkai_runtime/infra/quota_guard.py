"""配额守卫（实现 domain.ports.QuotaGuard 协议）——Phase 0 内存实现。

**边界**：billing 服务（T-007 域）落地后，配额/积分的真实判定与原子扣减归
billing；runtime 只发计量事件、不感知计费规则（docs/03 §3.4 横切机制②）。
本实现是 Phase 0 的过渡：按租户日 token 用量设上限，超限抛
QuotaExceededError（契约 429）。

已知限制（单实例）：计数在进程内存，重启清零、多副本不共享——
生产必须换 billing/Redis 实现（端口不变，services 层零改动）。
"""

from __future__ import annotations

from collections.abc import Mapping

from linkai_runtime.domain.errors import QuotaExceededError


class InMemoryQuotaGuard:
    """进程内配额守卫。"""

    def __init__(
        self,
        *,
        default_daily_tokens: int,
        tenant_daily_tokens: Mapping[str, int] | None = None,
    ) -> None:
        self._default = default_daily_tokens
        self._per_tenant = dict(tenant_daily_tokens or {})
        self._consumed: dict[str, int] = {}

    async def check(self, tenant_id: str, *, estimated_tokens: int) -> None:
        limit = self._per_tenant.get(tenant_id, self._default)
        used = self._consumed.get(tenant_id, 0)
        if used + max(estimated_tokens, 0) > limit:
            raise QuotaExceededError(
                f"租户 {tenant_id} 当日 token 配额不足："
                f"已用 {used}，本次预估 {estimated_tokens}，上限 {limit}"
            )

    async def record(self, tenant_id: str, *, tokens: int) -> None:
        self._consumed[tenant_id] = self._consumed.get(tenant_id, 0) + max(tokens, 0)
