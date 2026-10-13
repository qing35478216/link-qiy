"""充值订单领域模型 + 状态机（金额一律整数积分/分）。

状态机：
    pending ──pay──► paid ──refund──► refunded
       │                │
       └────close───────┴────close────► closed

- pay：仅 pending 可支付（重复支付/已关单支付 → OrderStateError）；
- close：pending（超时未付）或 paid（运营关单，不退款场景）可关；
- refund：仅 paid 可退款（退款返还积分走调账流水，Phase 2+）。
每次流转记录时间戳，供对账比对支付回调时序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from linkai_billing.domain.errors import OrderStateError
from linkai_billing.domain.ids import utcnow


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    CLOSED = "closed"
    REFUNDED = "refunded"


@dataclass
class RechargeOrder:
    """充值订单。credits/amount_fen 均为整数（铁律：禁浮点）。

    `request_id` 为创建幂等键（客户端供给）：同租户同键重复创建返回
    既有订单（DB 唯一约束兜底），防止网络重试产生重复单。
    """

    order_no: str  # 业务订单号（对外展示/回调关联）
    tenant_id: str
    request_id: str  # 创建幂等键
    package_code: str
    credits: int
    amount_fen: int
    status: OrderStatus = OrderStatus.PENDING
    provider: str = "mock"
    provider_trade_no: str | None = None
    # 回调幂等：支付渠道回调 ID（同回调 ID 重复投递只认一次）
    callback_id: str | None = None
    paid_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("RechargeOrder.tenant_id 不能为空（铁律 6）")
        if not isinstance(self.credits, int) or isinstance(self.credits, bool):
            raise TypeError("credits 必须为整数积分（禁浮点）")
        if not isinstance(self.amount_fen, int) or isinstance(self.amount_fen, bool):
            raise TypeError("amount_fen 必须为整数分（禁浮点）")
        if self.credits <= 0:
            raise ValueError("充值积分必须为正")
        if self.amount_fen <= 0:
            raise ValueError("充值金额（分）必须为正")

    # —— 状态机迁移（集中在此，禁止外部直接改 status）——

    def mark_paid(
        self, *, provider_trade_no: str, callback_id: str, now: datetime | None = None
    ) -> None:
        if self.status is not OrderStatus.PENDING:
            raise OrderStateError(f"订单 {self.order_no} 当前状态 {self.status}，不可支付")
        self.status = OrderStatus.PAID
        self.provider_trade_no = provider_trade_no
        self.callback_id = callback_id
        self.paid_at = now or utcnow()
        self.updated_at = self.paid_at

    def mark_closed(self, *, now: datetime | None = None) -> None:
        if self.status not in (OrderStatus.PENDING, OrderStatus.PAID):
            raise OrderStateError(f"订单 {self.order_no} 当前状态 {self.status}，不可关单")
        self.status = OrderStatus.CLOSED
        self.closed_at = now or utcnow()
        self.updated_at = self.closed_at

    def mark_refunded(self, *, now: datetime | None = None) -> None:
        if self.status is not OrderStatus.PAID:
            raise OrderStateError(f"订单 {self.order_no} 当前状态 {self.status}，不可退款")
        self.status = OrderStatus.REFUNDED
        self.updated_at = now or utcnow()
