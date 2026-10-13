"""领域端口（Protocol）——infra 实现、services 消费、domain 定义。

依赖倒置（铁律 2 四层）：domain 只定义接口；外部协作（model-proxy / platform /
DB / 配额）全部经端口注入，领域层零框架零 IO。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from linkai_runtime.domain.app_profile import AppProfile, KnowledgePolicy
from linkai_runtime.domain.assembly import KnowledgeHit
from linkai_runtime.domain.chat import ChatRequest, ChatResponse, StreamDelta
from linkai_runtime.domain.conversation import Conversation, Message
from linkai_runtime.domain.trace import ExecutionTrace


@dataclass(frozen=True, slots=True)
class TenantIdentity:
    """API Key 解析出的租户身份（用户面鉴权的产物）。"""

    tenant_id: str
    user_id: str | None
    key_id: str


@dataclass(frozen=True, slots=True)
class InvocationContext:
    """一次模型调用的横切上下文（tenant_id 必带，铁律 6）。"""

    tenant_id: str
    trace_id: str
    app_code: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id 不能为空（铁律 6）")


class ApiKeyResolver(Protocol):
    """API Key → 租户身份（用户面鉴权；platform Key 签发落地前的占位实现见 infra）。"""

    def resolve(self, key: str) -> TenantIdentity | None:
        """无效/吊销返回 None（调用方转 401）。"""
        ...


class AppProfileProvider(Protocol):
    """应用设定提供者（platform HTTP / Phase 0 静态注入）。"""

    async def get_profile(self, tenant_id: str, app_code: str) -> AppProfile | None:
        """应用不存在返回 None；平台不可达抛 AppConfigUnavailableError。"""
        ...


class ModelGateway(Protocol):
    """模型网关客户端（调 model-proxy 的 OpenAI 兼容端点）。"""

    async def complete(self, request: ChatRequest, ctx: InvocationContext) -> ChatResponse: ...

    def stream(
        self, request: ChatRequest, ctx: InvocationContext
    ) -> AsyncIterator[StreamDelta]: ...

    async def list_models(self, tenant_id: str) -> list[Mapping[str, object]]:
        """可调用模型元数据（透传 model-proxy /v1/models 的 data 项）。"""
        ...


class QuotaGuard(Protocol):
    """配额守卫（Phase 0 内存实现；billing 服务落地后替换，端口不变）。"""

    async def check(self, tenant_id: str, *, estimated_tokens: int) -> None:
        """超配额抛 QuotaExceededError（契约 429）。"""
        ...

    async def record(self, tenant_id: str, *, tokens: int) -> None:
        """记录实际消耗（模型调用成功后）。"""
        ...


class KnowledgeRetriever(Protocol):
    """知识库检索（本期无 knowledge 服务：Noop 实现返回空，miss 策略兜底）。"""

    async def retrieve(
        self, *, tenant_id: str, policy: KnowledgePolicy, query: str
    ) -> tuple[KnowledgeHit, ...]: ...


class ConversationRepository(Protocol):
    """会话/消息仓储（所有方法带 tenant_id，铁律 6）。"""

    def get(self, tenant_id: str, conversation_id: str) -> Conversation | None: ...

    def create(self, conversation: Conversation) -> None: ...

    def append_message(self, message: Message) -> None: ...

    def recent_messages(
        self, tenant_id: str, conversation_id: str, *, limit: int
    ) -> tuple[Message, ...]:
        """最近 limit 条消息，**时间序（旧 → 新）**返回。"""
        ...


class ExecutionTraceRepository(Protocol):
    """执行链仓储（trace_id 为主键，查询带 tenant_id）。"""

    def add(self, trace: ExecutionTrace) -> None: ...

    def get(self, tenant_id: str, trace_id: str) -> ExecutionTrace | None: ...
