"""内存端口实现——测试与无 DB 模式（dev）使用。

与 SQLAlchemy 实现同一批 domain 端口协议；单进程语义，不跨重启。
"""

from __future__ import annotations

from linkai_runtime.domain.assembly import KnowledgeHit
from linkai_runtime.domain.conversation import Conversation, Message
from linkai_runtime.domain.trace import ExecutionTrace, TraceStatus, TraceStep


class InMemoryConversationRepository:
    """内存会话仓储（(tenant_id, conversation_id) 复合键，天然隔离）。"""

    def __init__(self) -> None:
        self._conversations: dict[tuple[str, str], Conversation] = {}
        self._messages: dict[tuple[str, str], list[Message]] = {}

    def get(self, tenant_id: str, conversation_id: str) -> Conversation | None:
        return self._conversations.get((tenant_id, conversation_id))

    def create(self, conversation: Conversation) -> None:
        self._conversations[(conversation.tenant_id, conversation.id)] = conversation

    def append_message(self, message: Message) -> None:
        key = (message.tenant_id, message.conversation_id)
        seq = len(self._messages.get(key, ()))
        stored = Message(
            id=message.id,
            conversation_id=message.conversation_id,
            tenant_id=message.tenant_id,
            role=message.role,
            content=message.content,
            name=message.name,
            tool_call_id=message.tool_call_id,
            usage=message.usage,
            seq=seq,
            created_at=message.created_at,
        )
        self._messages.setdefault(key, []).append(stored)
        conversation = self._conversations.get(key)
        if conversation is not None:
            self._conversations[key] = Conversation(
                id=conversation.id,
                tenant_id=conversation.tenant_id,
                app_code=conversation.app_code,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=message.created_at,
            )

    def recent_messages(
        self, tenant_id: str, conversation_id: str, *, limit: int
    ) -> tuple[Message, ...]:
        rows = self._messages.get((tenant_id, conversation_id), [])
        return tuple(rows[-limit:]) if limit > 0 else ()


class InMemoryExecutionTraceRepository:
    """内存执行链仓储。"""

    def __init__(self) -> None:
        self._traces: dict[tuple[str, str], ExecutionTrace] = {}

    def add(self, trace: ExecutionTrace) -> None:
        self._traces[(trace.tenant_id, trace.trace_id)] = trace

    def get(self, tenant_id: str, trace_id: str) -> ExecutionTrace | None:
        return self._traces.get((tenant_id, trace_id))


class NoopKnowledgeRetriever:
    """知识库检索占位（knowledge 服务落地前返回空；miss 策略兜底）。"""

    async def retrieve(
        self, *, tenant_id: str, policy: object, query: str
    ) -> tuple[KnowledgeHit, ...]:
        return ()


class ScriptedKnowledgeRetriever:
    """测试用：返回预置命中（验证装配的知识库优先级路径）。"""

    def __init__(self, hits: tuple[KnowledgeHit, ...]) -> None:
        self._hits = hits

    async def retrieve(
        self, *, tenant_id: str, policy: object, query: str
    ) -> tuple[KnowledgeHit, ...]:
        return self._hits


def make_trace(
    *,
    trace_id: str,
    tenant_id: str,
    conversation_id: str,
    app_code: str | None,
    model: str,
    steps: tuple[TraceStep, ...] = (),
    status: TraceStatus = TraceStatus.OK,
) -> ExecutionTrace:
    """测试助手：直接构造执行链。"""
    return ExecutionTrace.create(
        trace_id=trace_id,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        app_code=app_code,
        model=model,
        steps=steps,
        status=status,
    )
