"""应用域仓储接口（domain 定义，infra 实现）。

tenant_id 过滤同账户域铁律：所有方法签名带 tenant_id，实现必须写入 WHERE。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from linkai_platform.domain.apps import App, AppConfig, AppVersion
from linkai_platform.domain.pagination import Cursor


@dataclass(frozen=True)
class AppPage:
    items: list[App]
    next_cursor: str | None  # 由 infra 用 domain/pagination 生成


class AppRepository(Protocol):
    def list_page(
        self,
        tenant_id: str,
        *,
        app_type: str | None,
        cursor: Cursor | None,
        limit: int,
    ) -> AppPage:
        """列表（created_at DESC, id DESC keyset 分页）。app_type=None 表示 all。"""
        ...

    def count(self, tenant_id: str, *, app_type: str | None = None) -> int: ...

    def get(self, tenant_id: str, app_id: str) -> App | None: ...

    def add(self, app: App) -> None: ...

    def save(self, app: App) -> None: ...

    def delete(self, tenant_id: str, app_id: str) -> None: ...


@dataclass(frozen=True)
class AppVersionPage:
    items: list[AppVersion]
    next_cursor: str | None


class AppVersionRepository(Protocol):
    def add(self, version: AppVersion) -> None: ...

    def get(self, tenant_id: str, app_id: str, version: int) -> AppVersion | None: ...

    def list_page(
        self,
        tenant_id: str,
        app_id: str,
        *,
        cursor: Cursor | None,
        limit: int,
    ) -> AppVersionPage:
        """版本历史（version DESC；cursor 用 created_at/id keyset）。"""
        ...

    def config_of(self, tenant_id: str, app_id: str, version: int) -> AppConfig | None:
        """取某版本配置内容（回滚用）；不存在返回 None。"""
        ...
