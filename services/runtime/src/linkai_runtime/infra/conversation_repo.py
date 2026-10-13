"""会话/消息仓储实现（SQLAlchemy）。

所有查询带 tenant_id 过滤（铁律 6）；seq 由仓储在 append 时按会话内最大值+1
分配（并发下取 max+1 有竞态，Phase 0 单写者路径可接受；严格序时需 DB 序列或锁）。
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from linkai_runtime.domain.chat import MessageRole, TokenUsage
from linkai_runtime.domain.conversation import Conversation, Message
from linkai_runtime.infra.db import ensure_aware
from linkai_runtime.infra.models import ConversationModel, MessageModel


def _to_conversation(row: ConversationModel) -> Conversation:
    return Conversation(
        id=row.id,
        tenant_id=row.tenant_id,
        app_code=row.app_code,
        title=row.title,
        created_at=ensure_aware(row.created_at),
        updated_at=ensure_aware(row.updated_at),
    )


def _to_message(row: MessageModel) -> Message:
    usage: TokenUsage | None = None
    if isinstance(row.usage_json, dict):
        prompt = row.usage_json.get("promptTokens")
        completion = row.usage_json.get("completionTokens")
        total = row.usage_json.get("totalTokens")
        credits = row.usage_json.get("credits", 0)
        if isinstance(prompt, int) and isinstance(completion, int) and isinstance(total, int):
            usage = TokenUsage(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                credits=credits if isinstance(credits, int) else 0,
            )
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        tenant_id=row.tenant_id,
        role=MessageRole(row.role),
        content=row.content,
        name=row.name,
        tool_call_id=row.tool_call_id,
        usage=usage,
        seq=row.seq,
        created_at=ensure_aware(row.created_at),
    )


def usage_to_json(usage: TokenUsage) -> dict[str, object]:
    return {
        "promptTokens": usage.prompt_tokens,
        "completionTokens": usage.completion_tokens,
        "totalTokens": usage.total_tokens,
        "credits": usage.credits,
    }


class SqlAlchemyConversationRepository:
    """会话仓储（实现 domain.ports.ConversationRepository 协议）。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def get(self, tenant_id: str, conversation_id: str) -> Conversation | None:
        with self._session() as session:
            row = session.get(ConversationModel, conversation_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return _to_conversation(row)

    def create(self, conversation: Conversation) -> None:
        with self._session() as session:
            session.add(
                ConversationModel(
                    id=conversation.id,
                    tenant_id=conversation.tenant_id,
                    app_code=conversation.app_code,
                    title=conversation.title,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            )
            session.commit()

    def append_message(self, message: Message) -> None:
        with self._session() as session:
            seq = (
                session.query(func.max(MessageModel.seq))
                .filter(
                    MessageModel.conversation_id == message.conversation_id,
                    MessageModel.tenant_id == message.tenant_id,
                )
                .scalar()
            )
            next_seq = (seq + 1) if seq is not None else 0
            session.add(
                MessageModel(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    tenant_id=message.tenant_id,
                    seq=next_seq,
                    role=str(message.role),
                    content=message.content,
                    name=message.name,
                    tool_call_id=message.tool_call_id,
                    usage_json=usage_to_json(message.usage) if message.usage else None,
                    created_at=message.created_at,
                )
            )
            # 会话 updated_at  touch（列表排序"最近活跃"）
            conv = session.get(ConversationModel, message.conversation_id)
            if conv is not None and conv.tenant_id == message.tenant_id:
                conv.updated_at = message.created_at
            session.commit()

    def recent_messages(
        self, tenant_id: str, conversation_id: str, *, limit: int
    ) -> tuple[Message, ...]:
        """最近 limit 条，时间序（旧 → 新）。"""
        with self._session() as session:
            rows = (
                session.query(MessageModel)
                .filter(
                    MessageModel.conversation_id == conversation_id,
                    MessageModel.tenant_id == tenant_id,
                )
                .order_by(MessageModel.seq.desc())
                .limit(limit)
                .all()
            )
            return tuple(_to_message(row) for row in reversed(rows))
