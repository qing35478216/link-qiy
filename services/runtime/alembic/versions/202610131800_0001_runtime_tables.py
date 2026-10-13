"""runtime 首批表：conversations / messages / execution_traces / api_keys。

与 platform 同库不同表（compose 单 PG 实例）；本服务只管理自身表。
api_keys 为 Phase 0 占位（platform Key 签发体系落地后下线，见 README 技术债）。

Revision ID: 0001_runtime_tables
Revises: None
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_runtime_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("app_code", sa.String(64), nullable=True),
        sa.Column("title", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_tenant", "conversations", ["tenant_id", "id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("name", sa.String(64), nullable=True),
        sa.Column("tool_call_id", sa.String(64), nullable=True),
        sa.Column("usage_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conv_seq", "messages", ["conversation_id", "seq"])

    op.create_table(
        "execution_traces",
        sa.Column("trace_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("app_code", sa.String(64), nullable=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("steps_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_traces_tenant", "execution_traces", ["tenant_id", "trace_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(64), nullable=False, server_default=""),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False, server_default=""),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # key_hash 唯一约束写在建表内（PG/SQLite 双兼容；SQLite 不支持
        # ALTER ADD CONSTRAINT，必须随表创建）
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_tenant", "api_keys", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("execution_traces")
    op.drop_table("messages")
    op.drop_table("conversations")
