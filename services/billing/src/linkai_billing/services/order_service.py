"""充值订单应用层：下单（幂等）/ Mock 支付 / 回调（验签+幂等）/ 关单。

资金不变量：
1. 金额一律整数积分/分（套餐定价即权威，客户端传金额无效——
   防篡改：下单只认 package_code）；
2. 创建幂等：同 (tenant_id, request_id) 重复创建返回既有订单；
3. 回调幂等：同订单重复回调只入账一次（订单状态机 + ledger request_id
   双重保证）；验签失败/重放窗口过期 → PaymentVerifyError（安全告警）；
4. 入账与订单状态迁移**同事务**：ledger.apply() 与 order.mark_paid()
   在同一会话事务，api 层统一提交——不会出现"钱到了单没改"。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from linkai_billing.domain.errors import OrderNotFound, OrderStateError
from linkai_billing.domain.ids import new_id, utcnow
from linkai_billing.domain.ledger import (
    LedgerApplyResult,
    LedgerEntry,
    LedgerEntryKind,
    LedgerEntryStatus,
    LedgerSource,
)
from linkai_billing.domain.orders import OrderStatus, RechargeOrder
from linkai_billing.domain.ports import (
    Clock,
    OrderRepository,
    PaymentProvider,
    WalletLedger,
)
from linkai_billing.domain.pricing import (
    ORDER_PAY_TIMEOUT_MINUTES,
    find_package,
)


@dataclass(frozen=True)
class OrderView:
    order_no: str
    tenant_id: str
    package_code: str
    credits: int
    amount_fen: int
    status: str
    provider: str
    provider_trade_no: str | None
    paid_at: datetime | None
    created_at: datetime


def _view(order: RechargeOrder) -> OrderView:
    return OrderView(
        order_no=order.order_no,
        tenant_id=order.tenant_id,
        package_code=order.package_code,
        credits=order.credits,
        amount_fen=order.amount_fen,
        status=str(order.status),
        provider=order.provider,
        provider_trade_no=order.provider_trade_no,
        paid_at=order.paid_at,
        created_at=order.created_at,
    )


@dataclass(frozen=True)
class PaymentCallbackResult:
    order_no: str
    credited: bool  # False = 幂等命中（重复回调，未重复入账）
    credits: int
    balance_after: int | None


class OrderService:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        ledger: WalletLedger,
        payment: PaymentProvider,
        clock: Clock | None = None,
    ) -> None:
        self._orders = orders
        self._ledger = ledger
        self._payment = payment
        self._clock = clock

    def _now(self) -> datetime:
        return self._clock.now() if self._clock is not None else utcnow()

    # —— 下单（幂等）——

    def create_order(
        self, *, tenant_id: str, package_code: str, request_id: str
    ) -> tuple[OrderView, bool]:
        """创建充值订单。返回 (订单, 是否新建)；同 request_id 重复创建返回既有订单。"""
        existing = self._orders.get_by_idempotency_key(tenant_id, request_id)
        if existing is not None:
            return _view(existing), False

        package = find_package(package_code)  # 四档之外拒绝（金额以套餐为准）
        order = RechargeOrder(
            order_no=f"RO{utcnow().strftime('%Y%m%d%H%M%S')}{new_id()[:8].upper()}",
            tenant_id=tenant_id,
            request_id=request_id,
            package_code=package.code,
            credits=package.credits,
            amount_fen=package.amount_fen,
            status=OrderStatus.PENDING,
            provider=self._payment.channel(),
        )
        self._orders.add(order)
        return _view(order), True

    def get_order(self, *, tenant_id: str, order_no: str) -> OrderView:
        order = self._orders.get(tenant_id, order_no)
        if order is None:
            raise OrderNotFound(f"订单不存在: {order_no}")
        return _view(order)

    def list_orders(
        self, *, tenant_id: str, status: str | None = None, limit: int = 50
    ) -> list[OrderView]:
        rows = self._orders.list_orders(
            tenant_id, status=OrderStatus(status) if status else None, limit=limit
        )
        return [_view(o) for o in rows]

    # —— Mock 支付（Phase 0：用户端点直接驱动"渠道扣款成功"）——

    def pay_order(self, *, tenant_id: str, order_no: str) -> PaymentCallbackResult:
        """Mock 支付：渠道扣款成功 → 走与真实回调**完全相同**的验签入账路径。"""
        order = self._require_order(tenant_id, order_no)
        prepay = self._payment.create_payment(
            order_no=order.order_no,
            amount_fen=order.amount_fen,
            description=f"积分充值 {order.credits}",
        )
        callback = self._payment.build_callback(
            order_no=order.order_no,
            amount_fen=order.amount_fen,
            callback_id=f"mock_cb_{order.order_no}",
            trade_no=str(prepay.get("prepayId", f"mock_trade_{order.order_no}")),
        )
        return self.handle_callback(callback)

    # —— 支付回调（验签 + 幂等 + 入账同事务）——

    def handle_callback(self, body: dict[str, object]) -> PaymentCallbackResult:
        """处理渠道回调（内部端点 /internal/v1/recharge/callback）。

        验签与重放窗口由 PaymentProvider.verify_callback 负责（失败即
        PaymentVerifyError，安全事件必须告警）；金额以**本地订单**为准
        （不信回调金额——防篡改）。
        """
        payload = self._payment.verify_callback(body)
        order_no = payload.get("orderNo", "")
        order = self._orders.get_by_order_no(order_no)
        if order is None:
            raise OrderNotFound(f"回调订单不存在: {order_no}")

        if order.status is OrderStatus.PAID:
            # 重复回调：幂等命中，绝不二次入账
            return PaymentCallbackResult(
                order_no=order.order_no, credited=False, credits=order.credits, balance_after=None
            )

        now = self._now()
        order.mark_paid(
            provider_trade_no=payload.get("tradeNo", ""),
            callback_id=payload.get("callbackId", ""),
            now=now,
        )
        # 入账（幂等键 = recharge:{order_no}；与订单状态迁移同事务）
        entry = LedgerEntry(
            entry_id=f"le_recharge_{order.order_no}",
            tenant_id=order.tenant_id,
            request_id=f"recharge:{order.order_no}",
            kind=LedgerEntryKind.RECHARGE,
            source=LedgerSource.ORDER,
            delta=order.credits,
            status=LedgerEntryStatus.APPLIED,
            credits_charged=order.credits,
            occurred_at=now,
        )
        applied = self._ledger.apply(entry)
        if applied.result is LedgerApplyResult.DUPLICATE:
            # 已入账过（极端：上次事务提交前崩溃重试）——订单状态照常推进
            pass
        try:
            # N2 条件保存：仅 pending → paid 才写回；并发方已支付则 rowcount=0
            self._orders.save(order, expect_status=(OrderStatus.PENDING,))
        except OrderStateError:
            # 并发回调落败：对方已把订单推向 paid——按幂等处理（重读最新态），
            # 不向渠道抛 5xx（渠道会重试，下次读到 PAID 走幂等分支）
            current = self._orders.get_by_order_no_fresh(order.order_no)
            if current is not None and current.status is OrderStatus.PAID:
                return PaymentCallbackResult(
                    order_no=current.order_no,
                    credited=False,
                    credits=current.credits,
                    balance_after=None,
                )
            raise
        return PaymentCallbackResult(
            order_no=order.order_no,
            credited=applied.result is not LedgerApplyResult.DUPLICATE,
            credits=order.credits,
            balance_after=applied.balance_after,
        )

    # —— 关单（超时未付）——

    def close_expired(self) -> list[str]:
        """关单超时 pending 订单（对账/定时任务调用）。返回被关订单号。"""
        expired = self._orders.find_expired_pending(
            now=self._now(), timeout_minutes=ORDER_PAY_TIMEOUT_MINUTES
        )
        closed: list[str] = []
        for order in expired:
            order.mark_closed(now=self._now())
            # 条件保存：仅仍在 pending 的才关（并发支付/关单不再覆盖）
            self._orders.save(order, expect_status=(OrderStatus.PENDING,))
            closed.append(order.order_no)
        return closed

    def _require_order(self, tenant_id: str, order_no: str) -> RechargeOrder:
        order = self._orders.get(tenant_id, order_no)
        if order is None:
            raise OrderNotFound(f"订单不存在: {order_no}")
        if order.status is OrderStatus.PENDING:
            return order
        raise OrderStateError(f"订单 {order_no} 当前状态 {order.status}，不可重复支付")
