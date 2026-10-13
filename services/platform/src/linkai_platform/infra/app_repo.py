"""AppRepository / AppVersionRepository 的 SQLAlchemy 实现。

tenant_id 强制过滤（铁律 6）；列表 keyset 分页（created_at DESC, id DESC），
cursor 生成用 domain/pagination 纯函数。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Select as _Select

from linkai_platform.domain.app_repositories import AppPage, AppVersionPage
from linkai_platform.domain.apps import App, AppConfig, AppVersion
from linkai_platform.domain.pagination import Cursor, encode_cursor
from linkai_platform.infra.app_config_codec import config_to_dict, dict_to_config
from linkai_platform.infra.db import ensure_aware
from linkai_platform.infra.models import AppModel, AppVersionModel


def _to_app(row: AppModel) -> App:
    return App(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        type=row.type,
        description=row.description,
        icon_url=row.icon_url,
        published=row.published,
        current_version=row.current_version,
        current_config=dict_to_config(row.current_config),
        created_at=ensure_aware(row.created_at),
        updated_at=ensure_aware(row.updated_at),
    )


def _to_version(row: AppVersionModel) -> AppVersion:
    return AppVersion(
        app_id=row.app_id,
        tenant_id=row.tenant_id,
        version=row.version,
        config=dict_to_config(row.config),
        source=row.source,
        created_at=ensure_aware(row.created_at),
    )


def _apply_cursor(stmt: _Select[Any], cursor: Cursor | None) -> _Select[Any]:
    if cursor is None:
        return stmt
    # keyset：(created_at, id) 严格小于 cursor 对应值
    return stmt.where(
        (AppModel.created_at < cursor.created_at)
        | ((AppModel.created_at == cursor.created_at) & (AppModel.id < cursor.id))
    )


class SqlAlchemyAppRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_page(
        self,
        tenant_id: str,
        *,
        app_type: str | None,
        cursor: Cursor | None,
        limit: int,
    ) -> AppPage:
        stmt = select(AppModel).where(AppModel.tenant_id == tenant_id)  # 强制租户过滤
        if app_type is not None and app_type != "all":
            stmt = stmt.where(AppModel.type == app_type)
        stmt = _apply_cursor(stmt, cursor)
        stmt = stmt.order_by(AppModel.created_at.desc(), AppModel.id.desc()).limit(limit)
        rows = list(self._session.execute(stmt).scalars())
        items = [_to_app(row) for row in rows]
        next_cursor = (
            encode_cursor(rows[-1].created_at, rows[-1].id) if len(rows) == limit else None
        )
        return AppPage(items=items, next_cursor=next_cursor)

    def count(self, tenant_id: str, *, app_type: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(AppModel)
            .where(AppModel.tenant_id == tenant_id)  # 强制租户过滤
        )
        if app_type is not None and app_type != "all":
            stmt = stmt.where(AppModel.type == app_type)
        return int(self._session.execute(stmt).scalar_one())

    def get(self, tenant_id: str, app_id: str) -> App | None:
        stmt = select(AppModel).where(
            AppModel.tenant_id == tenant_id,
            AppModel.id == app_id,  # 强制租户过滤
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        return None if row is None else _to_app(row)

    def add(self, app: App) -> None:
        self._session.add(
            AppModel(
                id=app.id,
                tenant_id=app.tenant_id,
                name=app.name,
                type=app.type,
                description=app.description,
                icon_url=app.icon_url,
                published=app.published,
                current_version=app.current_version,
                current_config=config_to_dict(app.current_config),
                created_at=app.created_at,
                updated_at=app.updated_at,
            )
        )

    def save(self, app: App) -> None:
        row = (
            self._session.query(AppModel)
            .filter(AppModel.tenant_id == app.tenant_id, AppModel.id == app.id)
            .one()
        )
        row.name = app.name
        row.type = app.type
        row.description = app.description
        row.icon_url = app.icon_url
        row.published = app.published
        row.current_version = app.current_version
        row.current_config = config_to_dict(app.current_config)
        row.updated_at = app.updated_at

    def delete(self, tenant_id: str, app_id: str) -> None:
        stmt = delete(AppModel).where(
            AppModel.tenant_id == tenant_id,
            AppModel.id == app_id,  # 强制租户过滤
        )
        self._session.execute(stmt)


class SqlAlchemyAppVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, version: AppVersion) -> None:
        self._session.add(
            AppVersionModel(
                app_id=version.app_id,
                tenant_id=version.tenant_id,
                version=version.version,
                source=version.source,
                config=config_to_dict(version.config),
                created_at=version.created_at,
            )
        )

    def get(self, tenant_id: str, app_id: str, version: int) -> AppVersion | None:
        stmt = select(AppVersionModel).where(
            AppVersionModel.tenant_id == tenant_id,  # 强制租户过滤
            AppVersionModel.app_id == app_id,
            AppVersionModel.version == version,
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        return None if row is None else _to_version(row)

    def list_page(
        self,
        tenant_id: str,
        app_id: str,
        *,
        cursor: Cursor | None,
        limit: int,
    ) -> AppVersionPage:
        stmt = select(AppVersionModel).where(
            AppVersionModel.tenant_id == tenant_id,  # 强制租户过滤
            AppVersionModel.app_id == app_id,
        )
        if cursor is not None:
            stmt = stmt.where(
                (AppVersionModel.created_at < cursor.created_at)
                | (
                    (AppVersionModel.created_at == cursor.created_at)
                    & (AppVersionModel.id < cursor.id)
                )
            )
        stmt = stmt.order_by(AppVersionModel.created_at.desc(), AppVersionModel.id.desc()).limit(
            limit
        )
        rows = list(self._session.execute(stmt).scalars())
        items = [_to_version(row) for row in rows]
        next_cursor = (
            encode_cursor(rows[-1].created_at, str(rows[-1].id)) if len(rows) == limit else None
        )
        return AppVersionPage(items=items, next_cursor=next_cursor)

    def config_of(self, tenant_id: str, app_id: str, version: int) -> AppConfig | None:
        found = self.get(tenant_id, app_id, version)
        return None if found is None else found.config
