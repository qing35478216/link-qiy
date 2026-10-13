"""充值订单/签到的 SQLAlchemy 实现（金额整数积分/分；铁律 6 查询带 tenant_id）。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from linkai_billing.domain.ids import utcnow
from linkai_billing.domain.orders import OrderStatus, RechargeOrder
from linkai_billing.infra.db import ensure_aware
from linkai_billing.infra.models import CheckInModel, RechargeOrderModel


def _order_to_entity(row: RechargeOrderModel) -> RechargeOrder:
    return RechargeOrder(
        order_no=row.order_no,
        tenant_id=row.tenant_id,
        request_id=row.request_id,
        package_code=row.package_code,
        credits=int(row.credits),
        amount_fen=int(row.amount_fen),
        status=OrderStatus(row.status),
        provider=row.provider,
        provider_trade_no=row.provider_trade_no,
        callback_id=row.callback_id,
        paid_at=None if row.paid_at is None else ensure_aware(row.paid_at),
        closed_at=None if row.closed_at is None else ensure_aware(row.closed_at),
        created_at=ensure_aware(row.created_at),
        updated_at=ensure_aware(row.updated_at),
    )


def _apply_order(order: RechargeOrder, row: RechargeOrderModel) -> None:
    row.status = str(order.status)
    row.provider = order.provider
    row.provider_trade_no = order.provider_trade_no
    row.callback_id = order.callback_id
    row.paid_at = order.paid_at
    row.closed_at = order.closed_at
    row.updated_at = utcnow()


class SqlAlchemyOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, order: RechargeOrder) -> None:
        self._session.add(
            RechargeOrderModel(
                order_no=order.order_no,
                tenant_id=order.tenant_id,
                request_id=order.request_id,
                package_code=order.package_code,
                credits=order.credits,
                amount_fen=order.amount_fen,
                status=str(order.status),
                provider=order.provider,
                provider_trade_no=order.provider_trade_no,
                callback_id=order.callback_id,
                paid_at=order.paid_at,
                closed_at=order.closed_at,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
        )
        self._session.flush()

    def get(self, tenant_id: str, order_no: str) -> RechargeOrder | None:
        row = self._session.execute(
            select(RechargeOrderModel).where(
                RechargeOrderModel.tenant_id == tenant_id,
                RechargeOrderModel.order_no == order_no,
            )
        ).scalar_one_or_none()
        return None if row is None else _order_to_entity(row)

    def get_by_order_no(self, order_no: str) -> RechargeOrder | None:
        """渠道回调全局定位（无租户上下文；定位后以订单行 tenant_id 为准）。"""
        row = self._session.execute(
            select(RechargeOrderModel).where(RechargeOrderModel.order_no == order_no)
        ).scalar_one_or_none()
        return None if row is None else _order_to_entity(row)

    def get_by_idempotency_key(self, tenant_id: str, request_id: str) -> RechargeOrder | None:
        row = self._session.execute(
            select(RechargeOrderModel).where(
                RechargeOrderModel.tenant_id == tenant_id,
                RechargeOrderModel.request_id == request_id,
            )
        ).scalar_one_or_none()
        return None if row is None else _order_to_entity(row)

    def list_orders(
        self,
        tenant_id: str,
        *,
        status: OrderStatus | None = None,
        limit: int = 50,
        before: tuple[datetime, str] | None = None,
    ) -> list[RechargeOrder]:
        stmt = select(RechargeOrderModel).where(RechargeOrderModel.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(RechargeOrderModel.status == str(status))
        if before is not None:
            stmt = stmt.where(
                (RechargeOrderModel.created_at < before[0])
                | (
                    (RechargeOrderModel.created_at == before[0])
                    & (RechargeOrderModel.order_no < before[1])
                )
            )
        stmt = stmt.order_by(
            RechargeOrderModel.created_at.desc(), RechargeOrderModel.order_no.desc()
        )
        stmt = stmt.limit(limit)
        return [_order_to_entity(row) for row in self._session.execute(stmt).scalars()]

    def find_expired_pending(self, *, now: datetime, timeout_minutes: int) -> list[RechargeOrder]:
        threshold = now - timedelta(minutes=timeout_minutes)
        stmt = select(RechargeOrderModel).where(
            RechargeOrderModel.status == str(OrderStatus.PENDING),
            RechargeOrderModel.created_at <= threshold,
        )
        return [_order_to_entity(row) for row in self._session.execute(stmt).scalars()]

    def save(self, order: RechargeOrder) -> None:
        row = self._session.execute(
            select(RechargeOrderModel).where(
                RechargeOrderModel.tenant_id == order.tenant_id,
                RechargeOrderModel.order_no == order.order_no,
            )
        ).scalar_one()
        _apply_order(order, row)
        self._session.flush()


class SqlAlchemyCheckInRepository:
    """签到仓储——(tenant_id, checkin_date) 唯一约束保证同日只加一次。

    `record` 返回 False = 当日已签到（唯一约束命中）。并发签到下先到者
    插入成功，后到者撞约束——SAVEPOINT 吸收 IntegrityError，外层事务
    不中毒（服务层零框架 import，拿 bool 即可判幂等）。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def has_checked_in(self, tenant_id: str, date: str) -> bool:
        row = self._session.execute(
            select(CheckInModel.id).where(
                CheckInModel.tenant_id == tenant_id,
                CheckInModel.checkin_date == date,
            )
        ).scalar_one_or_none()
        return row is not None

    def record(self, tenant_id: str, date: str, credits: int) -> bool:
        try:
            with self._session.begin_nested():
                self._session.add(
                    CheckInModel(
                        tenant_id=tenant_id,
                        checkin_date=date,
                        credits=credits,
                        created_at=utcnow(),
                    )
                )
                self._session.flush()
        except IntegrityError:
            return False  # 同日已签到（唯一约束）——幂等
        return True
