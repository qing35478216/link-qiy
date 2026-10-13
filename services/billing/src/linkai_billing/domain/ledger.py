"""统一计量流水（Ledger）——资金域的单一事实源。

设计要点（docs/03 §3.4② 统一计量）：
- 所有积分变动（扣减/充值/签到/调账）都落一条 append-only 流水，
  `wallets.balance` 只是流水的汇总视图；任何余额问题都能逐笔追溯；
- **幂等键 = request_id**（联合 tenant_id 唯一）：同一 request_id 的重复
  事件（MQ 重投、HTTP 重试、并发重复回调）只生效一次，由 DB 唯一约束
  硬保证（见 infra/wallet_repo.py 的条件 UPDATE + 唯一索引）；
- `delta` 为有符号整数积分（扣减为负、入账为正）；`balance_after` 快照
  便于对账时逐笔重放校验；
- `status=blocked` 的条目 delta=0：事件被记录但未扣减（余额不足），
  留痕供对账与运营分析——**不漏计也不多扣**。

铁律：金额/积分一律 int；本模块不 import 任何框架。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from linkai_billing.domain.ids import utcnow


class LedgerEntryKind(StrEnum):
    """流水业务类型。"""

    DEBIT = "debit"            # 计量扣减（模型调用等）
    RECHARGE = "recharge"      # 充值入账
    CHECKIN = "checkin"        # 签到奖励
    GRANT = "grant"            # 运营赠送/版本额度发放
    ADJUSTMENT = "adjustment"  # 人工调账（对账差异修复，须走审批流）


class LedgerSource(StrEnum):
    """流量来源——全维度流水的查询维度之一。"""

    METERING = "metering"  # model-proxy MeteringEvent
    ORDER = "order"        # 充值订单支付回调
    CHECKIN = "checkin"    # 签到
    SYSTEM = "system"      # 系统/运营


class LedgerEntryStatus(StrEnum):
    """条目生效状态。"""

    APPLIED = "applied"  # 已生效（余额已变动）
    BLOCKED = "blocked"  # 已留痕未扣减（余额不足；delta=0）


class LedgerApplyResult(StrEnum):
    """幂等写入的三种终态（服务层据此决定响应）。"""

    APPLIED = "applied"      # 本次写入生效
    DUPLICATE = "duplicate"  # request_id 已存在——幂等命中，未重复扣减
    BLOCKED = "blocked"      # 余额不足，留痕未扣减


@dataclass(frozen=True, slots=True)
class LedgerApplyOutcome:
    """apply() 的完整结果：终态 + 写入后余额快照（API/看板用）。"""

    result: LedgerApplyResult
    balance_after: int | None = None


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """一条积分流水（不可变；balance_after 为写入时快照）。"""

    entry_id: str
    tenant_id: str
    request_id: str  # 幂等键（调用方供给；计量事件 = event_id）
    kind: LedgerEntryKind
    source: LedgerSource
    delta: int  # 有符号积分；blocked 条目恒为 0
    status: LedgerEntryStatus = LedgerEntryStatus.APPLIED
    balance_after: int | None = None
    # —— 计量维度（全维度流水：来源/应用/模型/Token/耗时）——
    app_code: str | None = None
    model_code: str | None = None
    provider: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    credits_charged: int = 0  # 事件原始应扣积分（blocked 时 > 0 但 delta=0）
    latency_ms: int = 0
    outcome: str | None = None  # success/fallback_succeeded（MeteringOutcome）
    trace_id: str | None = None
    event_id: str | None = None
    conversation_id: str | None = None
    # DB 自增行号（keyset 分页游标用；内存假件为 0）
    row_id: int = 0
    occurred_at: datetime = field(default_factory=utcnow)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("LedgerEntry.tenant_id 不能为空（铁律 6）")
        if not self.request_id:
            raise ValueError("LedgerEntry.request_id（幂等键）不能为空")
        if not isinstance(self.delta, int) or isinstance(self.delta, bool):
            raise TypeError("delta 必须为整数积分（禁浮点）")
        if self.status is LedgerEntryStatus.BLOCKED and self.delta != 0:
            raise ValueError("blocked 条目 delta 必须为 0（留痕不扣减）")
        if self.kind is LedgerEntryKind.DEBIT and self.delta > 0:
            raise ValueError("DEBIT 条目 delta 必须 <= 0")
