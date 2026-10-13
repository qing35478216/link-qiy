"""T-003 应用域表：apps / app_versions

Revision ID: 0002_apps
Revises: 0001_account
Create Date: 2026-10-13 21:30:00

apps.current_config：七件套当前配置（JSON；缺段 = 已清空，PUT 全量替换语义）
app_versions：append-only 版本快照（save/snapshot/rollback 都产生新版本号）
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_apps"
down_revision = "0001_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("icon_url", sa.String(512), nullable=True),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_apps_tenant_created", "apps", ["tenant_id", "created_at", "id"])

    op.create_table(
        "app_versions",
        sa.Column("id", sa.Integer, autoincrement=True, primary_key=True),
        sa.Column("app_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("app_id", "version", name="uq_app_versions_app_version"),
    )
    op.create_index("ix_app_versions_tenant", "app_versions", ["tenant_id", "app_id"])


def downgrade() -> None:
    op.drop_table("app_versions")
    op.drop_table("apps")
