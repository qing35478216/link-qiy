"""Users 路由（契约 /me 段，bearerAuth + X-Tenant-Id）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from linkai_platform.api.deps import AppContext, get_context, get_principal
from linkai_platform.api.schemas import UserProfileResponse, UserProfileUpdateRequest
from linkai_platform.domain.auth import Principal
from linkai_platform.domain.users import User

router = APIRouter(tags=["Users"])


def _to_profile(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        id=user.id,
        nickname=user.nickname,
        avatarUrl=user.avatar_url,
        phone=user.phone,
        plan=user.plan.value,
        agreementAcceptedAt=user.agreement_accepted_at,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    principal: Principal = Depends(get_principal), ctx: AppContext = Depends(get_context)
) -> UserProfileResponse:
    user = ctx.user_service.get_profile(tenant_id=principal.tenant_id, user_id=principal.user_id)
    return _to_profile(user)


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    body: UserProfileUpdateRequest,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> UserProfileResponse:
    user = ctx.user_service.update_profile(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        nickname=body.nickname,
        avatar_url=body.avatarUrl,
        phone=body.phone,
    )
    return _to_profile(user)
