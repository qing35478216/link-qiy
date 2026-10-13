"""会话与消息领域对象（落库可回放的最小模型）。

多租户（铁律 6）：所有行归属 tenant_id，仓储查询必须带 tenant_id 过滤；
conversationId 续聊时校验"会话属于该租户"，不存在即 404（不泄露他租户存在性）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from linkai_runtime.domain.chat import MessageRole, TokenUsage


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Conversation:
    """一次会话（会话列表/续聊的最小单元）。"""

    id: str
    tenant_id: str
    app_code: str | None
    title: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        app_code: str | None,
        title: str = "",
        conversation_id: str | None = None,
    ) -> Conversation:
        now = utcnow()
        return cls(
            id=conversation_id or new_id(),
            tenant_id=tenant_id,
            app_code=app_code,
            title=title,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class Message:
    """一条消息（user/assistant；tool 角色为插件调用预留）。"""

    id: str
    conversation_id: str
    tenant_id: str
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    usage: TokenUsage | None = None
    seq: int = 0
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        *,
        conversation_id: str,
        tenant_id: str,
        role: MessageRole,
        content: str,
        seq: int,
        name: str | None = None,
        tool_call_id: str | None = None,
        usage: TokenUsage | None = None,
    ) -> Message:
        return cls(
            id=new_id(),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            name=name,
            tool_call_id=tool_call_id,
            usage=usage,
            seq=seq,
        )
