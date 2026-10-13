"""数据库引擎与会话（ORM 只允许在本层与 models.py 出现，铁律 2）。

与 platform 同构：同步 SQLAlchemy（Phase 0 约定）；runtime 热路径的流式循环
本身全异步，DB 落库点（会话开始/结束）经 services 层 asyncio.to_thread 包装，
不阻塞事件循环。PG16（compose 默认）与测试用 SQLite 均支持。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from linkai_runtime.infra.config import get_settings


class Base(DeclarativeBase):
    pass


def ensure_aware(dt: datetime) -> datetime:
    """SQLite 返回 naive datetime；统一视为 UTC，避免与 aware 时间比较报错。"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
