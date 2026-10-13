"""统一计量应用层：消费 MeteringEvent → 原子扣减积分（R-02）。

铁律落地（角色定义"不准在业务服务里写扣减逻辑"）：model-proxy 等入口
只发 MeteringEvent，扣减权威只在 billing 本服务；幂等键 = request_id
（= event_id），同一 request_id 重复事件只扣一次（并发用例证明）。

入账规则（写进工单交付说明的产品决策）：
1. **失败不计费**：outcome=FAILED 的事件按 delta=0 留痕（对账需要看到
   失败面，用于厂商成本核算与防刷分析）；
2. **余额不足不扣减**：BLOCKED 留痕（delta=0，credits_charged 记录应扣
   值）——绝不做部分扣减、绝不为负；事件终态化为 blocked，重试同一
   request_id 返回 DUPLICATE（防止补充值后被追溯扣旧账）；
3. **免费模型 0 积分**：delta=0 applied，流水可见。

事务：process() 不自行 commit——参与调用方事务（api 层统一提交），
与"事件 ACK"解耦：先落库提交、后 ACK，崩溃时未 ACK 事件重投，幂等
保证不重复扣减（至少一次 + 幂等 = 恰好一次效果）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from linkai_billing.domain.ids import utcnow
from linkai_billing.domain.ledger import (
    LedgerApplyResult,
    LedgerEntry,
    LedgerEntryKind,
    LedgerEntryStatus,
    LedgerSource,
)
from linkai_billing.domain.metering import MeteringEventIn
from linkai_billing.domain.ports import MeteringEventStream, WalletLedger
from linkai_billing.domain.pricing import CHECKIN_REWARD_CREDITS


@dataclass(frozen=True)
class DebitOutcome:
    """单条事件的处理终态（API/看板用）。"""

    request_id: str
    result: LedgerApplyResult
    credits_charged: int
    balance_after: int | None = None

    @property
    def deducted(self) -> bool:
        return self.result is LedgerApplyResult.APPLIED


class MeteringService:
    """计量事件消费（写路径）。"""

    def __init__(self, *, ledger: WalletLedger) -> None:
        self._ledger = ledger

    def process(self, event: MeteringEventIn) -> DebitOutcome:
        """处理一条计量事件（幂等；单事务内记流水+动余额）。"""
        billable = event.is_billable and event.credits > 0
        delta = -event.credits if billable else 0
        entry = LedgerEntry(
            entry_id=f"le_{event.request_id}",
            tenant_id=event.tenant_id,
            request_id=event.request_id,
            kind=LedgerEntryKind.DEBIT,
            source=LedgerSource.METERING,
            delta=delta,
            status=LedgerEntryStatus.APPLIED,
            app_code=event.app_code,
            model_code=event.model_code,
            provider=event.provider,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            total_tokens=event.total_tokens,
            credits_charged=event.credits,
            latency_ms=event.latency_ms,
            outcome=str(event.outcome),
            trace_id=event.trace_id,
            event_id=event.event_id,
            conversation_id=event.conversation_id,
            occurred_at=event.occurred_at or utcnow(),
        )
        applied = self._ledger.apply(entry)
        return DebitOutcome(
            request_id=event.request_id,
            result=applied.result,
            credits_charged=event.credits,
            balance_after=applied.balance_after,
        )

    def ingest(self, events: Iterable[MeteringEventIn]) -> list[DebitOutcome]:
        """批量消费（HTTP 批量端点/MQ 批处理共用）。"""
        return [self.process(event) for event in events]


class MeteringIngestService:
    """事件流水入口：XADD 入流 + 同步 drain（Phase 0）。

    Phase 0 同步 drain（请求内消费完再 ACK）——简单且立即可验证；
    Phase 1 迁 Celery worker（billing 队列，docs/03 §3.2）后本类只保留
    append，drain 由 worker 周期调用，端口不变。
    """

    def __init__(
        self,
        *,
        stream: MeteringEventStream,
        processor: Callable[[MeteringEventIn], DebitOutcome],
    ) -> None:
        self._stream = stream
        self._processor = processor

    def append(self, event: MeteringEventIn) -> str:
        payload = {
            "event_id": event.event_id,
            "tenant_id": event.tenant_id,
            "credits": str(event.credits),
            "outcome": str(event.outcome),
            "provider": event.provider,
            "model_code": event.model_code,
            "prompt_tokens": str(event.prompt_tokens),
            "completion_tokens": str(event.completion_tokens),
            "total_tokens": str(event.total_tokens),
            "latency_ms": str(event.latency_ms),
            "attempt": str(event.attempt),
            "occurred_at": (event.occurred_at or utcnow()).isoformat(),
        }
        if event.app_code is not None:
            payload["app_code"] = event.app_code
        if event.conversation_id is not None:
            payload["conversation_id"] = event.conversation_id
        if event.trace_id is not None:
            payload["trace_id"] = event.trace_id
        if event.error_code is not None:
            payload["error_code"] = event.error_code
        if event.fallback_from is not None:
            payload["fallback_from"] = event.fallback_from
        return self._stream.append(event.event_id, payload)

    def drain(self, *, consumer: str = "billing-worker", batch: int = 100) -> list[DebitOutcome]:
        """消费未处理条目（至少一次）；处理成功即 ACK，异常留未决重投。"""
        outcomes: list[DebitOutcome] = []
        for entry_id, payload in self._stream.read_group(consumer=consumer, count=batch):
            event = MeteringEventIn.from_payload(payload)
            outcome = self._processor(event)
            self._stream.ack(entry_id)
            outcomes.append(outcome)
        return outcomes

    def ingest(self, event: MeteringEventIn) -> DebitOutcome:
        """入流并立即 drain 本条（Phase 0 HTTP 端点路径）。"""
        self.append(event)
        drained = self.drain()
        for outcome in drained:
            if outcome.request_id == event.request_id:
                return outcome
        # 理论上不可达（append 后 drain 必含本条）；防御性返回重复态
        return DebitOutcome(
            request_id=event.request_id,
            result=LedgerApplyResult.DUPLICATE,
            credits_charged=event.credits,
        )


def build_checkin_entry(
    *, tenant_id: str, date: str, reward: int = CHECKIN_REWARD_CREDITS
) -> LedgerEntry:
    """签到入账流水（幂等键 = checkin:{tenant}:{date}，与签到记录双保险）。"""
    return LedgerEntry(
        entry_id=f"le_checkin_{tenant_id}_{date}",
        tenant_id=tenant_id,
        request_id=f"checkin:{tenant_id}:{date}",
        kind=LedgerEntryKind.CHECKIN,
        source=LedgerSource.CHECKIN,
        delta=reward,
        status=LedgerEntryStatus.APPLIED,
        credits_charged=reward,
        occurred_at=utcnow(),
    )
