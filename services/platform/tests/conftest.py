"""共享测试夹具：领域层内存假件 + API 层 TestClient（SQLite）。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from linkai_platform.domain.app_repositories import AppPage, AppVersionPage
from linkai_platform.domain.apps import App, AppVersion
from linkai_platform.domain.events import DomainEvent
from linkai_platform.domain.pagination import Cursor, encode_cursor
from linkai_platform.domain.repositories import (
    AccountRef,
    RefreshTokenRecord,
    RefreshTokenStore,
    UserRepository,
)
from linkai_platform.domain.users import User
from linkai_platform.infra.bus import InMemoryMessageBus


class FakeAppRepository:
    """内存应用仓储（(tenant_id, app_id) 复合键；keyset 分页同 SQL 实现语义）。"""

    def __init__(self) -> None:
        self._apps: dict[tuple[str, str], App] = {}

    def list_page(
        self,
        tenant_id: str,
        *,
        app_type: str | None,
        cursor: Cursor | None,
        limit: int,
    ) -> AppPage:
        rows = [
            a
            for (tid, _), a in self._apps.items()
            if tid == tenant_id and (app_type in (None, "all") or a.type == app_type)
        ]
        rows.sort(key=lambda a: (a.created_at, a.id), reverse=True)
        if cursor is not None:
            rows = [a for a in rows if (a.created_at, a.id) < (cursor.created_at, cursor.id)]
        page_rows = rows[:limit]
        next_cursor = (
            encode_cursor(page_rows[-1].created_at, page_rows[-1].id)
            if len(page_rows) == limit
            else None
        )
        return AppPage(items=page_rows, next_cursor=next_cursor)

    def count(self, tenant_id: str, *, app_type: str | None = None) -> int:
        return len(
            [
                a
                for (tid, _), a in self._apps.items()
                if tid == tenant_id and (app_type in (None, "all") or a.type == app_type)
            ]
        )

    def get(self, tenant_id: str, app_id: str) -> App | None:
        return self._apps.get((tenant_id, app_id))

    def add(self, app: App) -> None:
        self._apps[(app.tenant_id, app.id)] = app

    def save(self, app: App) -> None:
        self._apps[(app.tenant_id, app.id)] = app

    def delete(self, tenant_id: str, app_id: str) -> None:
        self._apps.pop((tenant_id, app_id), None)


class FakeAppVersionRepository:
    def __init__(self) -> None:
        self._versions: list[AppVersion] = []

    def add(self, version: AppVersion) -> None:
        self._versions.append(version)

    def get(self, tenant_id: str, app_id: str, version: int) -> AppVersion | None:
        for v in self._versions:
            if v.tenant_id == tenant_id and v.app_id == app_id and v.version == version:
                return v
        return None

    def list_page(
        self,
        tenant_id: str,
        app_id: str,
        *,
        cursor: Cursor | None,
        limit: int,
    ) -> AppVersionPage:
        rows = [v for v in self._versions if v.tenant_id == tenant_id and v.app_id == app_id]
        rows.sort(key=lambda v: (v.created_at, v.version), reverse=True)
        if cursor is not None:
            # versions 的 cursor.id 承载 str(version)
            threshold_version = int(cursor.id)
            rows = [
                v
                for v in rows
                if (v.created_at, v.version) < (cursor.created_at, threshold_version)
            ]
        page_rows = rows[:limit]
        next_cursor = (
            encode_cursor(page_rows[-1].created_at, str(page_rows[-1].version))
            if len(page_rows) == limit
            else None
        )
        return AppVersionPage(items=page_rows, next_cursor=next_cursor)

    def config_of(self, tenant_id: str, app_id: str, version: int):
        found = self.get(tenant_id, app_id, version)
        return None if found is None else found.config


class FakeUserRepository(UserRepository):
    """内存用户仓储（tenant_id 为复合键的一部分，天然隔离）。"""

    def __init__(self) -> None:
        self._users: dict[tuple[str, str], User] = {}

    def get(self, tenant_id: str, user_id: str) -> User | None:
        return self._users.get((tenant_id, user_id))

    def add(self, user: User) -> None:
        self._users[(user.tenant_id, user.id)] = user

    def save(self, user: User) -> None:
        self._users[(user.tenant_id, user.id)] = user


class FakeAccountDirectory:
    def __init__(self) -> None:
        self._by_phone: dict[str, AccountRef] = {}
        self._by_openid: dict[str, AccountRef] = {}

    def find_by_phone(self, phone: str) -> AccountRef | None:
        return self._by_phone.get(phone)

    def find_by_openid(self, openid: str) -> AccountRef | None:
        return self._by_openid.get(openid)

    def register(self, *, phone: str | None, openid: str | None, ref: AccountRef) -> None:
        if phone is not None:
            self._by_phone[phone] = ref
        if openid is not None:
            self._by_openid[openid] = ref


class FakeRefreshTokenStore(RefreshTokenStore):
    def __init__(self) -> None:
        self._records: dict[str, RefreshTokenRecord] = {}

    def save(self, record: RefreshTokenRecord) -> None:
        self._records[record.jti] = record

    def get(self, jti: str) -> RefreshTokenRecord | None:
        return self._records.get(jti)

    def revoke(self, jti: str) -> None:
        record = self._records.get(jti)
        if record is not None:
            self._records[jti] = RefreshTokenRecord(
                jti=record.jti,
                user_id=record.user_id,
                expires_at=record.expires_at,
                revoked=True,
            )

    def revoke_all_for_user(self, user_id: str) -> None:
        for jti, record in list(self._records.items()):
            if record.user_id == user_id and not record.revoked:
                self._records[jti] = RefreshTokenRecord(
                    jti=record.jti,
                    user_id=record.user_id,
                    expires_at=record.expires_at,
                    revoked=True,
                )


@pytest.fixture
def fake_users() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def fake_directory() -> FakeAccountDirectory:
    return FakeAccountDirectory()


@pytest.fixture
def fake_refresh_store() -> FakeRefreshTokenStore:
    return FakeRefreshTokenStore()


@pytest.fixture
def bus() -> InMemoryMessageBus:
    return InMemoryMessageBus()


@pytest.fixture
def published_events(bus: InMemoryMessageBus) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    bus.subscribe(events.append)
    return events


@pytest.fixture
def fake_apps() -> FakeAppRepository:
    return FakeAppRepository()


@pytest.fixture
def fake_app_versions() -> FakeAppVersionRepository:
    return FakeAppVersionRepository()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    """手机号登录一次，返回带 Bearer 的请求头（API 测试通用前置）。"""
    resp = client.post("/auth/phone/sms-code", json={"phone": "13800138000"})
    assert resp.status_code == 204
    code = client.app.state.sms_codes.peek_code("13800138000")  # type: ignore[attr-defined]
    assert code is not None
    resp = client.post(
        "/auth/phone/login",
        json={"phone": "13800138000", "smsCode": code, "agreementAccepted": True},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['accessToken']}"}


@pytest.fixture(autouse=True)
def _init_logging() -> None:
    """初始化结构化日志（未配置时 structlog 默认 PrintLogger 会绑定到错误的流）。"""
    from linkai_platform.infra.logging import setup_logging

    setup_logging("platform-test", "warning")


# —— API 层（TestClient + SQLite 文件库）——


@pytest.fixture
def client(tmp_path: Any) -> Iterator[TestClient]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from linkai_platform.infra import models  # noqa: F401  # 注册 ORM
    from linkai_platform.infra.config import Settings
    from linkai_platform.infra.db import Base, make_session_factory
    from linkai_platform.main import create_app

    # 内存库 + StaticPool：单连接共享，免落盘（沙箱 tmp 目录对并行 agent 不友好）
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    Base.metadata.create_all(engine)

    settings = Settings(
        service_name="platform",
        port=8000,
        log_level="warning",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-0123456789abcdef0123456789abcdef",  # noqa: S106 - 测试密钥
        access_token_ttl_seconds=3600,
        refresh_token_ttl_seconds=30 * 24 * 3600,
        sms_code_ttl_seconds=300,
        qr_ttl_seconds=300,
        wechat_mock_auto_confirm_seconds=0.0,
    )
    app = create_app(settings)
    app.state.session_factory = make_session_factory(engine)
    with TestClient(app) as test_client:
        yield test_client
