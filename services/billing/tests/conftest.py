"""共享测试夹具：内存假件 + API 层 TestClient（SQLite 文件库/内存库）。

两类 DB 用法：
- `client`（API 层）：SQLite 内存库 + StaticPool（单连接共享，免落盘）；
- `file_engine`/`session_factory`（并发层）：SQLite **文件**库 +
  每线程独立 Session——真实多连接写竞争，用于证明原子扣减/幂等的
  DB 级语义（唯一约束 + 条件 UPDATE）。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from linkai_billing.domain.metering import MeteringEventIn, MeteringOutcome
from linkai_billing.infra import models  # noqa: F401  # 注册 ORM
from linkai_billing.infra.config import Settings
from linkai_billing.infra.db import Base, make_session_factory
from linkai_billing.infra.memory_stream import InMemoryMeteringStream
from linkai_billing.main import create_app

TEST_SECRET = "test-secret-0123456789abcdef0123456789abcdef"
TEST_INTERNAL_TOKEN = "test-internal-token-0123456789"
TEST_PAYMENT_SECRET = "test-payment-secret-0123456789"


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "service_name": "billing-test",
        "port": 8010,
        "log_level": "warning",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": TEST_SECRET,
        "internal_token": TEST_INTERNAL_TOKEN,
        "payment_mock_secret": TEST_PAYMENT_SECRET,
        "redis_url": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def mint_token(*, tenant_id: str, user_id: str = "user-1") -> str:
    """签发测试用访问令牌（与 platform 同算法：HS256 + sub/tid claims）。"""
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "tid": tenant_id,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(claims, TEST_SECRET, algorithm="HS256")


@pytest.fixture
def settings() -> Settings:
    return make_settings()


# —— 文件库（并发用例）：每线程独立 Session，真实写竞争 ——


def _make_sqlite_engine(url: str, **kwargs: object) -> Engine:
    """SQLite 测试引擎（**事务语义对齐 PG 的关键适配**）。

    pysqlite 传统模式下 SAVEPOINT 会自启事务、RELEASE 即提交——这会让
    `begin_nested()`（幂等写入的 SAVEPOINT）在方法中途就把 ledger INSERT
    单独提交，"单事务原子扣减"在 SQLite 上形同虚设（已在 T-007-B1 复诊
    中实证：裸 sqlite3 双连接实验 + SQL echo 时序）。生产 PG（psycopg3）
    无此问题，但测试必须真实模拟事务语义，否则并发用例证明的是假不变量。
    适配 = SQLAlchemy 官方 recipe：autocommit + 连接级显式 BEGIN。
    """
    from sqlalchemy import event

    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30, "isolation_level": None},
        pool_pre_ping=True,
        **kwargs,  # type: ignore[arg-type]
    )

    @event.listens_for(engine, "connect")
    def _sqlite_autocommit(dbapi_connection: object, _record: object) -> None:
        # 关掉 pysqlite 的隐式 BEGIN（SAVEPOINT 不再自启事务）
        dbapi_connection.isolation_level = None  # type: ignore[attr-defined]
        # WAL：读写互不阻塞（PG 式 MVCC）。否则显式 BEGIN 下"读者持 SHARED
        # 锁挡写者提交、写者持 RESERVED 挡读者升级"会经典死锁（database is
        # locked 立即失败，busy handler 无法解开）。:memory: 不支持 WAL，
        # pragma 自动退化为 memory journal（单连接本无竞争）。
        dbapi_connection.execute("PRAGMA journal_mode=WAL")  # type: ignore[attr-defined]
        dbapi_connection.execute("PRAGMA busy_timeout=30000")  # type: ignore[attr-defined]

    @event.listens_for(engine, "begin")
    def _sqlite_begin(connection: object) -> None:
        # SQLAlchemy 事务开始时显式 BEGIN——SAVEPOINT 此后正确嵌套，
        # RELEASE 不再隐式提交（对照实验见 tests/services/test_atomic_debit.py）
        connection.exec_driver_sql("BEGIN")  # type: ignore[attr-defined]

    return engine


@pytest.fixture
def file_engine(tmp_path: Any) -> Iterator[Engine]:
    engine = _make_sqlite_engine(f"sqlite+pysqlite:///{tmp_path / 'billing.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def file_session_factory(file_engine: Engine) -> sessionmaker[Session]:
    return make_session_factory(file_engine)


# —— API 层：TestClient（内存库 + StaticPool）——


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = _make_sqlite_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = create_app(make_settings())
    app.state.session_factory = make_session_factory(engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_token(tenant_id='t-1')}"}


@pytest.fixture
def internal_headers() -> dict[str, str]:
    return {"X-Internal-Token": TEST_INTERNAL_TOKEN, "X-Tenant-Id": "t-1"}


def make_event(
    *,
    event_id: str = "evt-1",
    tenant_id: str = "t-1",
    credits: int = 100,
    outcome: MeteringOutcome = MeteringOutcome.SUCCESS,
    provider: str = "openai",
    model_code: str = "gpt-4o-mini",
    **kwargs: object,
) -> MeteringEventIn:
    defaults: dict[str, object] = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
        "latency_ms": 850,
        "attempt": 1,
        "trace_id": "trace-1",
        "app_code": "app-1",
        "conversation_id": "conv-1",
    }
    defaults.update(kwargs)
    return MeteringEventIn(
        event_id=event_id,
        tenant_id=tenant_id,
        credits=credits,
        outcome=outcome,
        provider=provider,
        model_code=model_code,
        **defaults,  # type: ignore[arg-type]
    )


@pytest.fixture
def event() -> MeteringEventIn:
    return make_event()


@pytest.fixture
def stream() -> InMemoryMeteringStream:
    return InMemoryMeteringStream()


@pytest.fixture(autouse=True)
def _init_logging() -> None:
    """初始化结构化日志（未配置时 structlog 默认 PrintLogger 绑定错误流）。"""
    from linkai_billing.infra.logging import setup_logging

    setup_logging("billing-test", "warning")


def run_in_threads(count: int, target: Any) -> list[Any]:
    """并发执行 target(index) 并收集结果/异常（真实线程竞争）。"""
    results: list[Any] = [None] * count
    errors: list[BaseException] = []
    barrier = threading.Barrier(count)

    def _worker(index: int) -> None:
        try:
            barrier.wait(timeout=10)  # 统一发令，最大化竞争窗口
            results[index] = target(index)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, f"线程异常: {errors}"
    return results
