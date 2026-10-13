"""T-002 账户域初始表：users / account_index / refresh_tokens

Revision ID: 0001_account
Revises:
Create Date: 2026-10-13 17:00:00

类型全部使用通用类型（String/DateTime），可在 PG16 与测试 SQLite 上执行。
users.tenant_id：工作租户过滤列（铁律 6），全部查询必须带该条件。
account_index：手机号/微信 openid 全局唯一自然键（登录定位，非租户数据）。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_account"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("nickname", sa.String(64), nullable=False),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("wechat_openid", sa.String(128), nullable=True),
        sa.Column("plan", sa.String(16), nullable=False, server_default="basic"),
        sa.Column("agreement_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_tenant", "users", ["tenant_id", "id"])

    op.create_table(
        "account_index",
        sa.Column("id", sa.Integer, autoincrement=True, primary_key=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("openid", sa.String(128), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("phone", name="uq_account_index_phone"),
        sa.UniqueConstraint("openid", name="uq_account_index_openid"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_refresh_tokens_user", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("account_index")
    op.drop_table("users")
