"""T-007 变现框架 v1 初始表。

wallets / ledger_entries / recharge_orders / checkins / reconciliation_runs

Revision ID: 0001_billing
Revises:
Create Date: 2026-10-14 10:00:00

类型全部使用通用类型（String/DateTime/Integer/BigInteger），可在 PG16 与
测试 SQLite 上执行。tenant_id 为租户过滤列（铁律 6），全部查询必须带该条件。
资金不变量由两条唯一约束保证：
- ledger_entries(tenant_id, request_id)：幂等键（同一 request_id 只入账一次）
- checkins(tenant_id, checkin_date)：同日签到只加一次
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_billing"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallets",
        sa.Column("tenant_id", sa.String(64), primary_key=True),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("plan", sa.String(16), nullable=False, server_default="basic"),
        sa.Column("reminder_threshold", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("low_balance_notified_on", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="applied"),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=True),
        sa.Column("app_code", sa.String(64), nullable=True),
        sa.Column("model_code", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("event_id", sa.String(64), nullable=True),
        sa.Column("conversation_id", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_ledger_tenant_request"),
    )
    op.create_index("ix_ledger_tenant_created", "ledger_entries", ["tenant_id", "created_at", "id"])
    op.create_index("ix_ledger_tenant_kind", "ledger_entries", ["tenant_id", "kind", "created_at"])
    op.create_index(
        "ix_ledger_tenant_app", "ledger_entries", ["tenant_id", "app_code", "created_at"]
    )
    op.create_table(
        "recharge_orders",
        sa.Column("order_no", sa.String(32), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("package_code", sa.String(32), nullable=False),
        sa.Column("credits", sa.BigInteger(), nullable=False),
        sa.Column("amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(32), nullable=False, server_default="mock"),
        sa.Column("provider_trade_no", sa.String(64), nullable=True),
        sa.Column("callback_id", sa.String(64), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_orders_tenant_request"),
    )
    op.create_index(
        "ix_orders_tenant_created", "recharge_orders", ["tenant_id", "created_at", "order_no"]
    )
    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("checkin_date", sa.String(10), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "checkin_date", name="uq_checkins_tenant_date"),
    )
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_scope", sa.String(32), nullable=False, server_default="global"),
        sa.Column("stream_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("db_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diff_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diff_ratio", sa.String(32), nullable=False, server_default="0"),
        sa.Column("alert", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_runs")
    op.drop_table("checkins")
    op.drop_table("recharge_orders")
    op.drop_index("ix_ledger_tenant_app", table_name="ledger_entries")
    op.drop_index("ix_ledger_tenant_kind", table_name="ledger_entries")
    op.drop_index("ix_ledger_tenant_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("wallets")
