"""迁移可移植性用例：alembic upgrade head 必须在 SQLite（测试）与 PG16（生产）都跑通。

背景（真实踩坑）：`create_unique_constraint` 在 SQLite 方言不被支持
（No support for ALTER of constraints），唯一约束必须随 create_table 声明。
本用例守住这条——PG 上跑得对不代表 SQLite 上跑得对。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


def test_upgrade_head_creates_runtime_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "migration-check.db"
    # alembic/env.py 按 platform 约定从 DATABASE_URL 环境变量读连接串
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")

    service_root = Path(__file__).resolve().parents[2]
    config = Config(str(service_root / "alembic.ini"))
    config.set_main_option("script_location", str(service_root / "alembic"))

    command.upgrade(config, "head")

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
    finally:
        conn.close()

    assert {
        "conversations",
        "messages",
        "execution_traces",
        "api_keys",
        "alembic_version",
    } <= tables
    # 迁移里声明的索引必须存在（租户过滤列，铁律 6）
    assert {
        "ix_conversations_tenant",
        "ix_messages_conv_seq",
        "ix_traces_tenant",
        "ix_api_keys_tenant",
    } <= indexes

    # downgrade 可回滚（向前兼容三步法的反向）
    command.downgrade(config, "base")
