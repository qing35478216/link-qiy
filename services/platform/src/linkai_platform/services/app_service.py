"""应用域编排（应用层）：CRUD + 配置七件套 + 版本 + 公开开关。

规则来源：
- PUT 配置为全量替换语义（契约 v0.1.1 description）；未提供段落清空
- 版本 append-only：PUT/快照/回滚都产生新版本号
- 公开开关切换发 AppPublished/AppUnpublished 内部领域事件（v0.2 再契约化外发）
- 创建前校验应用数配额（docs/01 四档矩阵）
"""

from __future__ import annotations

import structlog

from linkai_platform.domain import quota as quota_domain
from linkai_platform.domain.app_repositories import (
    AppPage,
    AppRepository,
    AppVersionPage,
    AppVersionRepository,
)
from linkai_platform.domain.apps import (
    App,
    AppConfig,
    AppNotFound,
    AppVersion,
    AppVersionNotFound,
)
from linkai_platform.domain.events import AppPublished, AppUnpublished, MessageBus
from linkai_platform.domain.pagination import decode_cursor
from linkai_platform.domain.repositories import UserRepository
from linkai_platform.domain.users import Plan, User, UserNotFound

logger = structlog.get_logger(__name__)

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class AppService:
    def __init__(
        self,
        *,
        apps: AppRepository,
        versions: AppVersionRepository,
        users: UserRepository,
        bus: MessageBus,
    ) -> None:
        self._apps = apps
        self._versions = versions
        self._users = users
        self._bus = bus

    # —— CRUD ——

    def create(
        self,
        *,
        tenant_id: str,
        user_id: str,
        name: str,
        type: str,
        description: str | None = None,
        icon_url: str | None = None,
    ) -> App:
        plan = self._plan_of(tenant_id, user_id)
        current = self._apps.count(tenant_id)
        quota_domain.assert_app_limit(plan, current)
        app = App.create(
            tenant_id=tenant_id, name=name, type=type, description=description, icon_url=icon_url
        )
        self._apps.add(app)
        logger.info("app_created", app_id=app.id, app_type=app.type, plan=plan.value)
        return app

    def list_apps(
        self, *, tenant_id: str, app_type: str | None, cursor: str | None, limit: int
    ) -> AppPage:
        return self._apps.list_page(
            tenant_id,
            app_type=app_type,
            cursor=decode_cursor(cursor) if cursor else None,
            limit=min(max(limit, 1), MAX_PAGE_LIMIT),
        )

    def get(self, *, tenant_id: str, app_id: str) -> App:
        app = self._apps.get(tenant_id, app_id)
        if app is None:
            raise AppNotFound("应用不存在或不属于当前租户")
        return app

    def update(
        self,
        *,
        tenant_id: str,
        app_id: str,
        name: str | None = None,
        description: str | None = None,
        icon_url: str | None = None,
    ) -> App:
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        app.update_basic(name=name, description=description, icon_url=icon_url)
        self._apps.save(app)
        return app

    def delete(self, *, tenant_id: str, app_id: str) -> None:
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        self._apps.delete(tenant_id, app.id)

    # —— 配置七件套 ——

    def get_config(self, *, tenant_id: str, app_id: str) -> AppConfig:
        return self.get(tenant_id=tenant_id, app_id=app_id).current_config

    def put_config(self, *, tenant_id: str, app_id: str, config: AppConfig) -> int:
        """全量替换配置（保存即新版本）。返回新版本号。"""
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        version = app.replace_config(config)
        self._apps.save(app)
        self._versions.add(self._snapshot_version(app, source="save"))
        logger.info("app_config_saved", app_id=app.id, version=version)
        return version

    def snapshot(self, *, tenant_id: str, app_id: str) -> int:
        """手动快照：当前配置记一个检查点版本。"""
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        version = app.snapshot()
        self._apps.save(app)
        self._versions.add(self._snapshot_version(app, source="snapshot"))
        return version

    def rollback(self, *, tenant_id: str, app_id: str, version: int) -> int:
        """回滚到指定版本：复制其配置内容为新版本（append-only）。"""
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        target = self._versions.get(tenant_id, app_id, version)
        if target is None:
            raise AppVersionNotFound(f"版本不存在: v{version}")
        new_version = app.rollback_to(target.config)
        self._apps.save(app)
        self._versions.add(self._snapshot_version(app, source="rollback"))
        logger.info("app_config_rollback", app_id=app.id, from_version=version, to=new_version)
        return new_version

    def list_versions(
        self, *, tenant_id: str, app_id: str, cursor: str | None, limit: int
    ) -> AppVersionPage:
        self.get(tenant_id=tenant_id, app_id=app_id)  # 404 保护 + 租户校验
        return self._versions.list_page(
            tenant_id,
            app_id,
            cursor=decode_cursor(cursor) if cursor else None,
            limit=min(max(limit, 1), MAX_PAGE_LIMIT),
        )

    # —— 公开开关 ——

    def publish(self, *, tenant_id: str, app_id: str) -> App:
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        if not app.published:
            app.publish()
            self._apps.save(app)
        self._bus.publish(
            AppPublished(app_id=app.id, tenant_id=app.tenant_id, version=app.current_version)
        )
        logger.info("app_published", app_id=app.id)
        return app

    def unpublish(self, *, tenant_id: str, app_id: str) -> App:
        app = self.get(tenant_id=tenant_id, app_id=app_id)
        if app.published:
            app.unpublish()
            self._apps.save(app)
        self._bus.publish(
            AppUnpublished(app_id=app.id, tenant_id=app.tenant_id, version=app.current_version)
        )
        logger.info("app_unpublished", app_id=app.id)
        return app

    # —— 内部 ——

    def _snapshot_version(self, app: App, *, source: str) -> AppVersion:
        return AppVersion(
            app_id=app.id,
            tenant_id=app.tenant_id,
            version=app.current_version,
            config=app.current_config,
            source=source,
            created_at=app.updated_at,
        )

    def _plan_of(self, tenant_id: str, user_id: str) -> Plan:
        user: User | None = self._users.get(tenant_id, user_id)
        if user is None:
            raise UserNotFound("用户不存在或不属于当前租户")
        return user.plan
