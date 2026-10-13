"""七件套配置编解码 + 应用仓储 tenant 隔离 + 分页（SQLite 真实 ORM）。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from linkai_platform.domain.apps import App, AppConfig, BasicConfig, ModelPromptConfig
from linkai_platform.infra import models  # noqa: F401  # 注册 ORM
from linkai_platform.infra.app_config_codec import config_to_dict, dict_to_config
from linkai_platform.infra.app_repo import (
    SqlAlchemyAppRepository,
    SqlAlchemyAppVersionRepository,
)
from linkai_platform.infra.db import Base, make_engine, make_session_factory


def test_codec_roundtrip() -> None:
    config = AppConfig(
        basic=BasicConfig(welcomeMessage="你好", guideQuestions=["a", "b"]),
        modelPrompt=ModelPromptConfig(modelCode="gpt-4o", temperature=0.7, memoryRounds=5),
    )
    data = config_to_dict(config)
    assert data["basic"]["welcomeMessage"] == "你好"
    assert data["modelPrompt"]["temperature"] == 0.7
    assert dict_to_config(data) == config


def test_codec_empty_config() -> None:
    assert config_to_dict(AppConfig.empty()) == {}
    assert dict_to_config(None) == AppConfig.empty()
    assert dict_to_config({}) == AppConfig.empty()


def test_codec_ignores_unknown_segments() -> None:
    config = dict_to_config({"basic": {"welcomeMessage": "x"}, "unknownSegment": {"a": 1}})
    assert config.basic is not None and config.basic.welcomeMessage == "x"


@pytest.fixture
def session() -> Session:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = make_session_factory(engine)()
    try:
        yield sess
        sess.commit()
    finally:
        sess.close()


def _new_app(tenant_id: str, name: str) -> App:
    return App.create(tenant_id=tenant_id, name=name, type="lightweight")


def test_app_cross_tenant_isolation(session: Session) -> None:
    """验收标准 5：应用仓储 tenant 强制过滤。"""
    repo = SqlAlchemyAppRepository(session)
    app = _new_app("tenant-a", "A的应用")
    repo.add(app)
    session.flush()

    assert repo.get("tenant-a", app.id) is not None
    assert repo.get("tenant-b", app.id) is None  # 跨租户越读被过滤
    assert repo.count("tenant-b") == 0
    # 跨租户删除无效
    repo.delete("tenant-b", app.id)
    session.flush()
    assert repo.get("tenant-a", app.id) is not None


def test_app_save_cannot_move_across_tenant(session: Session) -> None:
    from sqlalchemy.orm.exc import NoResultFound

    repo = SqlAlchemyAppRepository(session)
    app = _new_app("tenant-a", "x")
    repo.add(app)
    session.flush()
    app.tenant_id = "attacker"
    with pytest.raises(NoResultFound):
        repo.save(app)


def test_app_version_cross_tenant(session: Session) -> None:
    repo = SqlAlchemyAppVersionRepository(session)
    app = _new_app("tenant-a", "x")
    from linkai_platform.domain.apps import AppVersion

    repo.add(
        AppVersion(
            app_id=app.id,
            tenant_id="tenant-a",
            version=1,
            config=AppConfig(basic=BasicConfig(welcomeMessage="v1")),
            source="save",
            created_at=app.created_at,
        )
    )
    session.flush()
    assert repo.get("tenant-a", app.id, 1) is not None
    assert repo.get("tenant-b", app.id, 1) is None
    assert repo.config_of("tenant-b", app.id, 1) is None


def test_app_list_keyset_pagination(session: Session) -> None:
    repo = SqlAlchemyAppRepository(session)
    base = _new_app("seed-tenant", "seed").created_at  # seed 放别的租户，不干扰计数
    for i in range(5):
        app = _new_app("tenant-a", f"app{i}")
        app.created_at = base + timedelta(seconds=i)  # 稳定排序键（先设后落库）
        repo.add(app)
    session.flush()

    page1 = repo.list_page("tenant-a", app_type=None, cursor=None, limit=2)
    assert [a.name for a in page1.items] == ["app4", "app3"]  # created_at DESC
    assert page1.next_cursor is not None  # 恰好取满一页 → 给游标（是否存在下一页由下一拉验证）
    # 不足一页（limit > 总数）→ 无游标
    page_full = repo.list_page("tenant-a", app_type=None, cursor=None, limit=6)
    assert len(page_full.items) == 5 and page_full.next_cursor is None
    # cursor 续拉：从第 2 条起应拿到 app2/app1/app0
    from linkai_platform.domain.pagination import decode_cursor

    cursor = decode_cursor(page1.next_cursor)
    page2 = repo.list_page("tenant-a", app_type=None, cursor=cursor, limit=5)
    assert [a.name for a in page2.items] == ["app2", "app1", "app0"]
