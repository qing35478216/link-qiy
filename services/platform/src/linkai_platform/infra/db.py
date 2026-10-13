"""数据库引擎与会话（ORM 只允许在本层与 models.py 出现）。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from linkai_platform.infra.config import get_settings


class Base(DeclarativeBase):
    pass


def ensure_aware(dt: datetime) -> datetime:
    """SQLite 返回 naive datetime；统一视为 UTC，避免与 aware 时间比较报错。

    PG（DateTime(timezone=True)）原样返回 aware 时间，本函数对 aware 输入是恒等映射。
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """请求级会话依赖：提交成功即 flush，异常回滚。"""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
