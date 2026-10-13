"""仓库层 tenant_id 强制过滤证明（验收标准 4）：SQLite 真实 ORM 验证。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from linkai_platform.domain.users import User
from linkai_platform.infra import models  # noqa: F401  # 注册 ORM
from linkai_platform.infra.db import Base, make_engine, make_session_factory
from linkai_platform.infra.user_repo import SqlAlchemyUserRepository


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        yield sess
        sess.commit()
    finally:
        sess.close()


def test_cross_tenant_read_returns_none(session: Session) -> None:
    repo = SqlAlchemyUserRepository(session)
    user = User.register_with_phone("13800138000")
    repo.add(user)
    session.flush()

    assert repo.get(user.tenant_id, user.id) is not None
    assert repo.get("other-tenant", user.id) is None  # 跨租户越读被过滤


def test_save_cannot_move_user_across_tenant(session: Session) -> None:
    from sqlalchemy.orm.exc import NoResultFound

    repo = SqlAlchemyUserRepository(session)
    user = User.register_with_phone("13800138000")
    repo.add(user)
    session.flush()

    # 模拟攻击：把实体 tenant_id 改成别的租户再 save
    user.tenant_id = "attacker-tenant"
    with pytest.raises(NoResultFound):  # WHERE tenant_id 过滤使目标行不可见
        repo.save(user)
