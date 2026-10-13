"""Apps 路由（契约 console-api.yaml Apps 段：CRUD + 配置七件套 + 公开开关 + 版本）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from linkai_platform.api.deps import AppContext, get_context, get_principal
from linkai_platform.api.schemas import (
    AppConfigIn,
    AppConfigOut,
    AppCreateRequest,
    AppResponse,
    AppUpdateRequest,
    AppVersionItem,
    PageResponse,
    VersionResponse,
)
from linkai_platform.domain.apps import App
from linkai_platform.domain.auth import Principal
from linkai_platform.infra.app_config_codec import config_to_dict, dict_to_config

router = APIRouter(tags=["Apps"])


def _to_response(app: App) -> AppResponse:
    return AppResponse(
        id=app.id,
        name=app.name,
        description=app.description,
        type=app.type,
        iconUrl=app.icon_url,
        published=app.published,
        currentVersion=app.current_version,
        createdAt=app.created_at,
        updatedAt=app.updated_at,
    )


@router.get("/apps", response_model=PageResponse)
async def list_apps(
    type: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> PageResponse:
    page = ctx.app_service.list_apps(
        tenant_id=principal.tenant_id, app_type=type, cursor=cursor, limit=limit
    )
    return PageResponse(items=[_to_response(a) for a in page.items], nextCursor=page.next_cursor)


@router.post("/apps", response_model=AppResponse, status_code=201)
async def create_app(
    body: AppCreateRequest,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> AppResponse:
    app = ctx.app_service.create(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        name=body.name,
        type=body.type,
        description=body.description,
        icon_url=body.iconUrl,
    )
    return _to_response(app)


@router.get("/apps/{appId}", response_model=AppResponse)
async def get_app(
    appId: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> AppResponse:
    return _to_response(ctx.app_service.get(tenant_id=principal.tenant_id, app_id=appId))


@router.patch("/apps/{appId}", response_model=AppResponse)
async def update_app(
    appId: str,
    body: AppUpdateRequest,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> AppResponse:
    app = ctx.app_service.update(
        tenant_id=principal.tenant_id,
        app_id=appId,
        name=body.name,
        description=body.description,
        icon_url=body.iconUrl,
    )
    return _to_response(app)


@router.delete("/apps/{appId}", status_code=204)
async def delete_app(
    appId: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> Response:
    ctx.app_service.delete(tenant_id=principal.tenant_id, app_id=appId)
    return Response(status_code=204)


@router.get("/apps/{appId}/config", response_model=AppConfigOut)
async def get_app_config(
    appId: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> AppConfigOut:
    config = ctx.app_service.get_config(tenant_id=principal.tenant_id, app_id=appId)
    return AppConfigOut(**config_to_dict(config))


@router.put("/apps/{appId}/config", response_model=VersionResponse)
async def put_app_config(
    appId: str,
    body: AppConfigIn,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> VersionResponse:
    # 全量替换：exclude_none 丢弃未提供字段 → 缺段清空（契约 v0.1.1 PUT 语义）
    config = dict_to_config(body.model_dump(exclude_none=True))
    version = ctx.app_service.put_config(tenant_id=principal.tenant_id, app_id=appId, config=config)
    return VersionResponse(version=version)


@router.post("/apps/{appId}/publish", response_model=AppResponse)
async def publish_app(
    appId: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> AppResponse:
    return _to_response(ctx.app_service.publish(tenant_id=principal.tenant_id, app_id=appId))


@router.delete("/apps/{appId}/publish", status_code=204)
async def unpublish_app(
    appId: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> Response:
    ctx.app_service.unpublish(tenant_id=principal.tenant_id, app_id=appId)
    return Response(status_code=204)


@router.get("/apps/{appId}/versions", response_model=PageResponse)
async def list_app_versions(
    appId: str,
    cursor: str | None = None,
    limit: int = 20,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> PageResponse:
    page = ctx.app_service.list_versions(
        tenant_id=principal.tenant_id, app_id=appId, cursor=cursor, limit=limit
    )
    items = [
        AppVersionItem(version=v.version, source=v.source, createdAt=v.created_at)
        for v in page.items
    ]
    return PageResponse(items=list(items), nextCursor=page.next_cursor)


@router.post("/apps/{appId}/versions", response_model=VersionResponse, status_code=201)
async def snapshot_app_config(
    appId: str,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> VersionResponse:
    version = ctx.app_service.snapshot(tenant_id=principal.tenant_id, app_id=appId)
    return VersionResponse(version=version)


@router.post("/apps/{appId}/versions/{version}/rollback", response_model=VersionResponse)
async def rollback_app_config(
    appId: str,
    version: int,
    principal: Principal = Depends(get_principal),
    ctx: AppContext = Depends(get_context),
) -> VersionResponse:
    new_version = ctx.app_service.rollback(
        tenant_id=principal.tenant_id, app_id=appId, version=version
    )
    return VersionResponse(version=new_version)
