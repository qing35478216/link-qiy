"""钱包路由（控制台面）：余额查询 / 签到 / 提醒阈值。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from linkai_billing.api.deps import AppContext, get_context, get_principal
from linkai_billing.api.schemas import CheckInResponse, ReminderThresholdRequest, WalletResponse
from linkai_billing.domain.auth import Principal

router = APIRouter(prefix="/v1/wallet", tags=["Wallet"])


@router.get("", response_model=WalletResponse)
async def get_wallet(
    principal: Principal = Depends(get_principal), ctx: AppContext = Depends(get_context)
) -> WalletResponse:
    view = ctx.wallet_service.get_wallet(principal.tenant_id)
    return WalletResponse(
        tenantId=view.tenant_id,
        balance=view.balance,
        plan=view.plan,
        reminderThreshold=view.reminder_threshold,
        lowBalance=view.low_balance,
        shouldRemind=view.should_remind,
    )


@router.post("/check-in", response_model=CheckInResponse)
async def check_in(
    principal: Principal = Depends(get_principal), ctx: AppContext = Depends(get_context)
) -> CheckInResponse:
    """每日签到（幂等：同日重复只加一次；UTC 日期口径）。"""
    result = ctx.wallet_service.check_in(principal.tenant_id)
    return CheckInResponse(
        tenantId=result.tenant_id,
        date=result.date,
        creditsGranted=result.credits_granted,
        already=result.already,
        balanceAfter=result.balance_after,
    )


@router.put("/reminder-threshold", response_model=WalletResponse)
async def set_reminder_threshold(
    body: ReminderThresholdRequest,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> WalletResponse:
    view = ctx.wallet_service.set_reminder_threshold(principal.tenant_id, body.threshold)
    return WalletResponse(
        tenantId=view.tenant_id,
        balance=view.balance,
        plan=view.plan,
        reminderThreshold=view.reminder_threshold,
        lowBalance=view.low_balance,
        shouldRemind=view.should_remind,
    )
