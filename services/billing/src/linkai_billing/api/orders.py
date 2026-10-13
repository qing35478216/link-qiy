"""充值订单路由（控制台面）：套餐列表 / 下单（幂等）/ Mock 支付 / 订单列表。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from linkai_billing.api.deps import AppContext, get_context, get_principal
from linkai_billing.api.schemas import (
    CreateOrderRequest,
    OrderResponse,
    PayOrderResponse,
    RechargePackageResponse,
)
from linkai_billing.domain.auth import Principal
from linkai_billing.domain.pricing import RECHARGE_PACKAGES
from linkai_billing.services.order_service import OrderView

router = APIRouter(prefix="/v1/recharge", tags=["Recharge"])


@router.get("/packages", response_model=list[RechargePackageResponse])
async def list_packages(ctx: AppContext = Depends(get_context)) -> list[RechargePackageResponse]:
    """四档充值套餐（docs/01 第十部分实测；金额为整数分）。"""
    return [
        RechargePackageResponse(
            code=p.code,
            credits=p.credits,
            amountFen=p.amount_fen,
            amountYuan=p.amount_yuan_display,
            label=p.label,
            tag=p.tag,
        )
        for p in RECHARGE_PACKAGES
    ]


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    body: CreateOrderRequest,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> OrderResponse:
    """创建充值订单（幂等：同 requestId 重复创建返回既有订单）。"""
    view, _created = ctx.order_service.create_order(
        tenant_id=principal.tenant_id,
        package_code=body.packageCode,
        request_id=body.requestId,
    )
    return _order_response(view)


@router.post("/orders/{order_no}/pay", response_model=PayOrderResponse)
async def pay_order(
    order_no: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> PayOrderResponse:
    """Mock 支付（Phase 0）：渠道扣款成功 → 验签入账（同真实回调路径）。"""
    result = ctx.order_service.pay_order(tenant_id=principal.tenant_id, order_no=order_no)
    return PayOrderResponse(
        orderNo=result.order_no,
        credited=result.credited,
        credits=result.credits,
        balanceAfter=result.balance_after,
    )


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> list[OrderResponse]:
    views = ctx.order_service.list_orders(
        tenant_id=principal.tenant_id, status=status, limit=limit
    )
    return [_order_response(v) for v in views]


def _order_response(view: OrderView) -> OrderResponse:
    return OrderResponse(
        orderNo=view.order_no,
        tenantId=view.tenant_id,
        packageCode=view.package_code,
        credits=view.credits,
        amountFen=view.amount_fen,
        status=view.status,
        provider=view.provider,
        providerTradeNo=view.provider_trade_no,
        paidAt=view.paid_at,
        createdAt=view.created_at,
    )
