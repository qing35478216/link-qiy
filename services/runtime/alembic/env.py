"""Alembic 运行环境：从环境变量读 DATABASE_URL；metadata 来自 infra ORM 模型。"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# prepend_sys_path = src（alembic.ini）保证可导入
from linkai_runtime.infra import models  # noqa: F401  # 注册表模型
from linkai_runtime.infra.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL 不入库：环境变量优先，缺省用 compose 本地值
database_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://linkai:linkai_dev_password@localhost:5432/linkai",
)
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
