"""对账校准（R-05）：Redis 事件流水 vs DB 积分明细比对（纯函数核心）。

比对口径：
- 以 `request_id`（= event_id）为关联键，双侧各自去重后集合比对；
- 差异分类：
  - `missing_in_db`：流水有、DB 无——**危险**（用户被漏计或消费丢失，
    差异率超阈值自动告警并冻结结算，AGENTS.md 工程规范）；
  - `missing_in_stream`：DB 有、流水无——消费成功但入流失败/被截断，
    需补投；
  - `amount_mismatch`：双侧都有但积分不一致——折算规则漂移或篡改，
    最高优先级人工复核；
- 差异率 = 差异条目数 / max(流水的条目数, 1)；> 0.01% 即告警（工程规范）。

本模块为纯函数（无 IO）：services 层负责取数，domain 负责判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkai_billing.domain.ledger import LedgerEntryKind

#: 对账差异告警阈值（工程规范：>0.01% 自动告警并冻结结算）
RECONCILIATION_ALERT_RATIO = 0.0001


@dataclass(frozen=True, slots=True)
class StreamRecord:
    """流水侧一条记录（Redis Stream 条目投影）。"""

    request_id: str
    credits: int


@dataclass(frozen=True, slots=True)
class DbRecord:
    """DB 侧一条记录（计量扣减流水投影）。"""

    request_id: str
    credits: int
    applied: bool  # status=applied（blocked 条目不参与金额比对）


@dataclass(frozen=True)
class ReconciliationReport:
    """对账结果（值对象；可直出看板/告警）。"""

    stream_count: int = 0
    db_count: int = 0
    matched: int = 0
    missing_in_db: tuple[str, ...] = ()
    missing_in_stream: tuple[str, ...] = ()
    amount_mismatch: tuple[tuple[str, int, int], ...] = ()  # (request_id, 流水积分, DB积分)
    blocked_count: int = 0
    diff_ratio: float = 0.0
    alert: bool = False
    notes: dict[str, int] = field(default_factory=dict)

    @property
    def diff_count(self) -> int:
        return len(self.missing_in_db) + len(self.missing_in_stream) + len(self.amount_mismatch)

    def summary_line(self) -> str:
        return (
            f"stream={self.stream_count} db={self.db_count} matched={self.matched} "
            f"missing_in_db={len(self.missing_in_db)} "
            f"missing_in_stream={len(self.missing_in_stream)} "
            f"amount_mismatch={len(self.amount_mismatch)} "
            f"diff_ratio={self.diff_ratio:.6%} alert={self.alert}"
        )


def reconcile(
    *,
    stream: list[StreamRecord],
    db: list[DbRecord],
    alert_ratio: float = RECONCILIATION_ALERT_RATIO,
) -> ReconciliationReport:
    """比对流水与 DB 明细（纯函数；双侧按 request_id 去重，重复侧取首条）。"""
    stream_by_id: dict[str, StreamRecord] = {}
    for record in stream:
        stream_by_id.setdefault(record.request_id, record)

    db_by_id: dict[str, DbRecord] = {}
    for db_record in db:
        db_by_id.setdefault(db_record.request_id, db_record)

    missing_in_db = sorted(set(stream_by_id) - set(db_by_id))
    missing_in_stream = sorted(set(db_by_id) - set(stream_by_id))

    mismatches: list[tuple[str, int, int]] = []
    matched = 0
    for request_id, s in stream_by_id.items():
        d = db_by_id.get(request_id)
        if d is None:
            continue
        if not d.applied:
            # blocked（余额不足留痕）：DB 侧存在即视为对齐，金额不比对
            matched += 1
            continue
        if s.credits != d.credits:
            mismatches.append((request_id, s.credits, d.credits))
        else:
            matched += 1
    mismatches.sort()

    blocked_count = sum(1 for d in db_by_id.values() if not d.applied)
    diff_count = len(missing_in_db) + len(missing_in_stream) + len(mismatches)
    denominator = max(len(stream_by_id), 1)
    diff_ratio = diff_count / denominator
    alert = diff_ratio > alert_ratio

    return ReconciliationReport(
        stream_count=len(stream_by_id),
        db_count=len(db_by_id),
        matched=matched,
        missing_in_db=tuple(missing_in_db),
        missing_in_stream=tuple(missing_in_stream),
        amount_mismatch=tuple(mismatches),
        blocked_count=blocked_count,
        diff_ratio=diff_ratio,
        alert=alert,
    )


def debit_kind() -> LedgerEntryKind:
    """对账只比对计量扣减流水（充值/签到不入事件流水）。"""
    return LedgerEntryKind.DEBIT
