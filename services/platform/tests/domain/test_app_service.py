"""应用域编排单测（内存假件）。"""

from __future__ import annotations

import pytest

from linkai_platform.domain.apps import (
    AppConfig,
    AppLimitExceeded,
    AppNotFound,
    AppVersionNotFound,
    BasicConfig,
    ModelPromptConfig,
)
from linkai_platform.domain.events import AppPublished, AppUnpublished
from linkai_platform.domain.users import Plan, User
from linkai_platform.infra.bus import InMemoryMessageBus
from linkai_platform.services.app_service import AppService
from linkai_platform.services.quota_service import QuotaService
from tests.conftest import (
    FakeAppRepository,
    FakeAppVersionRepository,
    FakeUserRepository,
)


def make_service(
    *,
    apps: FakeAppRepository | None = None,
    versions: FakeAppVersionRepository | None = None,
    users: FakeUserRepository | None = None,
    bus: InMemoryMessageBus | None = None,
    plan: Plan = Plan.BASIC,
) -> tuple[AppService, list[object]]:
    bus = bus or InMemoryMessageBus()
    events: list[object] = []
    bus.subscribe(events.append)
    users = users or FakeUserRepository()
    user = User.register_with_phone("13800138000")
    user.plan = plan
    users.add(user)
    service = AppService(
        apps=apps or FakeAppRepository(),
        versions=versions or FakeAppVersionRepository(),
        users=users,
        bus=bus,
    )
    return service, events


def test_create_and_get() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="助手", type="lightweight")
    fetched = service.get(tenant_id=user.tenant_id, app_id=app.id)
    assert fetched.id == app.id and fetched.name == "助手"


def test_create_respects_basic_plan_limit() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    for i in range(3):  # 基础版 3 个
        service.create(
            tenant_id=user.tenant_id, user_id=user.id, name=f"app{i}", type="lightweight"
        )
    with pytest.raises(AppLimitExceeded):
        service.create(tenant_id=user.tenant_id, user_id=user.id, name="app4", type="lightweight")


def test_create_enterprise_unlimited() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    user.plan = Plan.ENTERPRISE
    users.add(user)
    service, _ = make_service(users=users, plan=Plan.ENTERPRISE)
    for i in range(12):
        service.create(tenant_id=user.tenant_id, user_id=user.id, name=f"app{i}", type="knowledge")


def test_get_unknown_app_raises() -> None:
    service, _ = make_service()
    with pytest.raises(AppNotFound):
        service.get(tenant_id="t-x", app_id="no-such-app")


def test_update_and_delete() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="旧", type="lightweight")
    updated = service.update(tenant_id=user.tenant_id, app_id=app.id, name="新")
    assert updated.name == "新"
    service.delete(tenant_id=user.tenant_id, app_id=app.id)
    with pytest.raises(AppNotFound):
        service.get(tenant_id=user.tenant_id, app_id=app.id)


def test_put_config_full_replace_and_version() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="x", type="lightweight")

    v1 = service.put_config(
        tenant_id=user.tenant_id,
        app_id=app.id,
        config=AppConfig(modelPrompt=ModelPromptConfig(modelCode="gpt-4o")),
    )
    assert v1 == 1
    config = service.get_config(tenant_id=user.tenant_id, app_id=app.id)
    assert config.modelPrompt is not None and config.modelPrompt.modelCode == "gpt-4o"

    # 全量替换：只给 basic，modelPrompt 清空
    v2 = service.put_config(
        tenant_id=user.tenant_id,
        app_id=app.id,
        config=AppConfig(basic=BasicConfig(welcomeMessage="hi")),
    )
    assert v2 == 2
    config = service.get_config(tenant_id=user.tenant_id, app_id=app.id)
    assert config.modelPrompt is None
    assert config.basic is not None and config.basic.welcomeMessage == "hi"


def test_snapshot_and_rollback() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="x", type="lightweight")
    service.put_config(
        tenant_id=user.tenant_id,
        app_id=app.id,
        config=AppConfig(basic=BasicConfig(welcomeMessage="v1")),
    )
    snap = service.snapshot(tenant_id=user.tenant_id, app_id=app.id)
    assert snap == 2
    service.put_config(
        tenant_id=user.tenant_id,
        app_id=app.id,
        config=AppConfig(basic=BasicConfig(welcomeMessage="v2")),
    )
    new_version = service.rollback(tenant_id=user.tenant_id, app_id=app.id, version=1)
    assert new_version == 4  # append-only：回滚也产生新版本
    config = service.get_config(tenant_id=user.tenant_id, app_id=app.id)
    assert config.basic.welcomeMessage == "v1"


def test_rollback_unknown_version() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="x", type="lightweight")
    with pytest.raises(AppVersionNotFound):
        service.rollback(tenant_id=user.tenant_id, app_id=app.id, version=99)


def test_list_versions_pagination() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="x", type="lightweight")
    for i in range(3):
        service.put_config(
            tenant_id=user.tenant_id,
            app_id=app.id,
            config=AppConfig(basic=BasicConfig(welcomeMessage=f"v{i}")),
        )
    page = service.list_versions(tenant_id=user.tenant_id, app_id=app.id, cursor=None, limit=2)
    assert len(page.items) == 2
    assert page.next_cursor is not None
    page2 = service.list_versions(
        tenant_id=user.tenant_id, app_id=app.id, cursor=page.next_cursor, limit=2
    )
    assert len(page2.items) == 1
    versions = [v.version for v in page.items + page2.items]
    assert versions == [3, 2, 1]  # 版本 DESC


def test_publish_emits_event_and_is_idempotent() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, events = make_service(users=users)
    app = service.create(tenant_id=user.tenant_id, user_id=user.id, name="x", type="lightweight")
    service.publish(tenant_id=user.tenant_id, app_id=app.id)
    assert isinstance(events[-1], AppPublished)
    service.publish(tenant_id=user.tenant_id, app_id=app.id)  # 幂等切换仍发事件
    published_events = [e for e in events if isinstance(e, AppPublished)]
    assert len(published_events) == 2

    service.unpublish(tenant_id=user.tenant_id, app_id=app.id)
    assert isinstance(events[-1], AppUnpublished)
    fetched = service.get(tenant_id=user.tenant_id, app_id=app.id)
    assert fetched.published is False


def test_list_apps_type_filter() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    service, _ = make_service(users=users)
    service.create(tenant_id=user.tenant_id, user_id=user.id, name="lw", type="lightweight")
    service.create(tenant_id=user.tenant_id, user_id=user.id, name="kb", type="knowledge")
    all_page = service.list_apps(tenant_id=user.tenant_id, app_type=None, cursor=None, limit=20)
    kb_page = service.list_apps(
        tenant_id=user.tenant_id, app_type="knowledge", cursor=None, limit=20
    )
    assert len(all_page.items) == 2
    assert [a.name for a in kb_page.items] == ["kb"]


def test_quota_service_summary() -> None:
    users = FakeUserRepository()
    user = User.register_with_phone("13800138000")
    users.add(user)
    quota_service = QuotaService(users=users)
    summary = quota_service.get_summary(tenant_id=user.tenant_id, user_id=user.id)
    assert summary.plan == "basic"
    assert summary.planBadge == "基础版"
    assert summary.walletBalance == 0  # 占位（T-007 对接）
    assert summary.usage is not None
