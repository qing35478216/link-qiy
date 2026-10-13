"""ORM 模型（铁律 2：只允许出现在 infra 层）。

表设计（T-007 变现框架 v1，迁移见 alembic/versions/0001_billing.py）：
- wallets：租户积分钱包（tenant_id 主键；balance 为整数积分）
- ledger_entries：积分流水（append-only；(tenant_id, request_id) 唯一
  ——幂等键的 DB 硬保证；source/kind/app_code/model_code 为查询维度）
- recharge_orders：充值订单（金额整数分；状态机 pending/paid/closed/refunded）
- checkins：签到记录（(tenant_id, checkin_date) 唯一——同日幂等）
- reconciliation_runs：对账运行记录（差异率超阈值告警留痕）

类型全部使用通用类型（String/DateTime/Integer/BigInteger），保证迁移可在
PG16 与测试 SQLite 上执行。所有查询必须带 tenant_id 过滤（铁律 6）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from linkai_billing.infra.db import Base


class WalletModel(Base):
    __tablename__ = "wallets"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 整数积分（BigInteger：企业版年度额度 100 万+ 充值累计可达千万级）
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    plan: Mapped[str] = mapped_column(String(16), nullable=False, default="basic")
    reminder_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    low_balance_notified_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LedgerEntryModel(Base):
    """积分流水（append-only；金额/积分全部整数列）。"""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 幂等键：联合唯一约束（DB 级"同一 request_id 只生效一次"）
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # —— 计量维度（全维度流水）——
    app_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # 幂等硬保证：同租户同 request_id 只能有一条流水
        UniqueConstraint("tenant_id", "request_id", name="uq_ledger_tenant_request"),
        Index("ix_ledger_tenant_created", "tenant_id", "created_at", "id"),
        Index("ix_ledger_tenant_kind", "tenant_id", "kind", "created_at"),
        Index("ix_ledger_tenant_app", "tenant_id", "app_code", "created_at"),
    )


class RechargeOrderModel(Base):
    __tablename__ = "recharge_orders"

    order_no: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 创建幂等键（客户端供给；同键重复创建返回既有订单）
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    package_code: Mapped[str] = mapped_column(String(32), nullable=False)
    credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_fen: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    provider_trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 回调幂等：渠道回调 ID（同回调 ID 重复投递只认一次）
    callback_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_orders_tenant_request"),
        Index("ix_orders_tenant_created", "tenant_id", "created_at", "order_no"),
    )


class CheckInModel(Base):
    """签到记录（(tenant_id, checkin_date) 唯一——DB 级同日幂等）。"""

    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    checkin_date: Mapped[str] = mapped_column(String(10), nullable=False)  # UTC YYYY-MM-DD
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "checkin_date", name="uq_checkins_tenant_date"),
    )


class ReconciliationRunModel(Base):
    """对账运行记录（差异率超阈值即告警留痕，供财务复核）。"""

    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    run_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    stream_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    db_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_ratio: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
