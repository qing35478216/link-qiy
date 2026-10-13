"""ORM 模型（铁律 2：只允许出现在 infra 层）。

runtime 自有表（与 platform 同库不同表，经 alembic 版本化管理）：
- conversations：会话（tenant_id 复合过滤）
- messages：消息（conversation_id + seq 时间序）
- execution_traces：执行链（trace_id 主键，steps 为 JSON 快照，可回放）
- api_keys：用户 API Key（**Phase 0 占位**：platform Key 签发体系落地后下线，
  见 README「技术债」；只存 SHA-256 哈希 + 前缀，绝不存明文）

类型全部使用通用类型（String/DateTime/JSON），保证迁移可在 PG16 与测试用
SQLite 上执行。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from linkai_runtime.infra.db import Base


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_conversations_tenant", "tenant_id", "id"),)


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: 该条消息的用量（assistant 消息落 model-proxy 回传的 usage，含 credits）
    usage_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_messages_conv_seq", "conversation_id", "seq"),)


class ExecutionTraceModel(Base):
    __tablename__ = "execution_traces"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    app_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    #: steps JSON 快照（TraceStep.to_dict 列表）——调试窗回放的事实源
    steps_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_traces_tenant", "tenant_id", "trace_id"),)


class ApiKeyModel(Base):
    """Phase 0 占位表（技术债：应由 platform 持有，见 README）。"""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: SHA-256(key) 十六进制；全局唯一自然键
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: 明文前缀（展示/排障用，如 "sk-…abcd"），不回显全量
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_api_keys_tenant", "tenant_id", "id"),)
