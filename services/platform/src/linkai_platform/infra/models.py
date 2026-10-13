"""ORM 模型（铁律 2：只允许出现在 infra 层）。

表设计（T-002 账户域，迁移见 alembic/versions/0001_account.py）：
- users：用户聚合，tenant_id 为其工作租户；全部查询必须带 tenant_id 过滤
- account_index：账户目录，手机号/微信 openid 为全局唯一自然键（登录定位用）
- refresh_tokens：刷新令牌 jti 状态（吊销/轮换）

类型全部使用通用类型（String/DateTime），保证迁移可在 PG16 与测试用 SQLite 上执行。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from linkai_platform.infra.db import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # 工作租户（Phase 0 个人租户 = user_id；铁律 6：查询必须过滤该列）
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    plan: Mapped[str] = mapped_column(String(16), nullable=False, default="basic")
    agreement_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_users_tenant", "tenant_id", "id"),)


class AccountIndexModel(Base):
    """账户目录：自然键 → (tenant_id, user_id)。phone/openid 全局唯一。"""

    __tablename__ = "account_index"

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    openid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)

    __table_args__ = (
        UniqueConstraint("phone", name="uq_account_index_phone"),
        UniqueConstraint("openid", name="uq_account_index_openid"),
    )


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AppModel(Base):
    """应用聚合。tenant_id 为工作租户（铁律 6：查询必须过滤）。"""

    __tablename__ = "apps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 当前生效配置（七件套 JSON；None 段落表示已清空——PUT 全量替换语义）
    current_config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_apps_tenant_created", "tenant_id", "created_at", "id"),)


class AppVersionModel(Base):
    """配置版本快照（append-only；回滚也产生新版本）。"""

    __tablename__ = "app_versions"

    id: Mapped[int] = mapped_column(autoincrement=True, primary_key=True)
    app_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # save|snapshot|rollback
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("app_id", "version", name="uq_app_versions_app_version"),
        Index("ix_app_versions_tenant", "tenant_id", "app_id"),
    )
