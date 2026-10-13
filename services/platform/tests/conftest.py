"""共享测试夹具：领域层内存假件 + API 层 TestClient（SQLite）。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from linkai_platform.domain.events import DomainEvent
from linkai_platform.domain.repositories import (
    AccountRef,
    RefreshTokenRecord,
    RefreshTokenStore,
    UserRepository,
)
from linkai_platform.domain.users import User
from linkai_platform.infra.bus import InMemoryMessageBus


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
