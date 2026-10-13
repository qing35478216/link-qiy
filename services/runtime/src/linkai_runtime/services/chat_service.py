"""对话编排服务（应用层）——一次对话的完整用例。

流程（流式/非流式共用前置链）：
  1. 会话确保（conversationId 续聊校验租户归属；缺省新建）
  2. 应用设定解析（appCode → AppProfileProvider；无 appCode = OpenAI 直通模式）
  3. 知识库检索（本期 Noop；配了知识库且未命中 → miss 策略注记）
  4. 上下文装配（domain 纯函数 assemble_context）
  5. 配额预检（QuotaGuard.check，超限 → 429/QUOTA_EXCEEDED）
  6. 模型调用（model-proxy；流式消费增量、非流式一次性）
  7. 落库（user/assistant 消息 + ExecutionTrace 执行链）+ 配额记账

事件协议（runtime-events.yaml v0.1.1，流式）：
  node_started → message_chunk*(seq 从 0) → done(usage+finishReason)
  异常终局：error(code/message/retriable)——消费端不依赖连接关闭。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog

from linkai_runtime.domain.app_profile import AppProfile
from linkai_runtime.domain.assembly import (
    DEFAULT_MEMORY_ROUNDS,
    AssembledContext,
    AssemblyInput,
    KnowledgeHit,
    assemble_context,
)
from linkai_runtime.domain.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    FinishReason,
    MessageRole,
    TokenUsage,
)
from linkai_runtime.domain.conversation import Conversation, Message
from linkai_runtime.domain.errors import (
    ConversationNotFoundError,
    DomainError,
    InvalidRequestError,
)
from linkai_runtime.domain.events import (
    EventEnvelope,
    done,
    error,
    message_chunk,
    node_started,
)
from linkai_runtime.domain.ports import (
    AppProfileProvider,
    ConversationRepository,
    ExecutionTraceRepository,
    InvocationContext,
    KnowledgeRetriever,
    ModelGateway,
    QuotaGuard,
    TenantIdentity,
)
from linkai_runtime.domain.tokens import estimate_tokens
from linkai_runtime.domain.trace import (
    ExecutionTrace,
    TraceStatus,
    TraceStep,
    TraceStepKind,
)

logger = structlog.get_logger(__name__)

#: model-proxy 在执行链中的插件名（观测规范名）
_MODEL_PLUGIN_NAME = "model-proxy"
#: 装配步骤在执行链中的插件名
_ASSEMBLY_PLUGIN_NAME = "runtime.assembly"


@dataclass(frozen=True, slots=True)
class ChatOutcome:
    """一次对话的结果（非流式返回）。"""

    response: ChatResponse
    conversation_id: str
    trace_id: str
    assembled: AssembledContext


@dataclass(frozen=True, slots=True)
class _Prepared:
    """前置链产物（流式/非流式共用）。"""

    request: ChatRequest
    ctx: InvocationContext
    conversation_id: str
    model_code: str
    assembled: AssembledContext
    assembly_step: TraceStep
    question: str
    profile: AppProfile | None


class ChatService:
    """对话用例编排（无框架依赖：全部协作经 domain 端口）。"""

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        traces: ExecutionTraceRepository,
        profiles: AppProfileProvider,
        gateway: ModelGateway,
        quota: QuotaGuard,
        knowledge: KnowledgeRetriever,
    ) -> None:
        self._conversations = conversations
        self._traces = traces
        self._profiles = profiles
        self._gateway = gateway
        self._quota = quota
        self._knowledge = knowledge

    # ── 非流式 ────────────────────────────────────────────────

    async def complete(
        self, request: ChatRequest, *, identity: TenantIdentity, trace_id: str
    ) -> ChatOutcome:
        prepared = await self._prepare(request, identity=identity, trace_id=trace_id)
        started = time.monotonic()
        response = await self._gateway.complete(prepared.request, prepared.ctx)
        duration_ms = int((time.monotonic() - started) * 1000)
        await self._persist_success(prepared, response=response, duration_ms=duration_ms)
        return ChatOutcome(
            response=response,
            conversation_id=prepared.conversation_id,
            trace_id=trace_id,
            assembled=prepared.assembled,
        )

    # ── 流式（Runtime Event 序列）─────────────────────────────

    async def stream_events(
        self, request: ChatRequest, *, identity: TenantIdentity, trace_id: str
    ) -> AsyncIterator[EventEnvelope]:
        conversation_id = request.conversation_id or ""
        steps: list[TraceStep] = []
        content_parts: list[str] = []
        final_usage: TokenUsage | None = None
        final_finish: FinishReason = FinishReason.STOP
        status: TraceStatus = TraceStatus.OK
        failure: Exception | None = None
        prepared: _Prepared | None = None
        got_done = False

        try:
            # 先确保会话存在：node_started 信封的 conversationId 必须非空
            # （契约：所有事件必带，用于乱序重组与对账）
            conversation = await self._ensure_conversation(request, identity)
            conversation_id = conversation.id
            yield node_started(
                trace_id=trace_id,
                conversation_id=conversation_id,
                node_type="llm",
                node_name=request.app_code or "chat",
            )
            prepared = await self._prepare(
                request, identity=identity, trace_id=trace_id, conversation=conversation
            )
            steps.append(prepared.assembly_step)
            async for delta in self._gateway.stream(prepared.request, prepared.ctx):
                if delta.is_terminal:
                    final_usage = delta.usage
                    if delta.finish_reason is not None:
                        final_finish = delta.finish_reason
                    continue
                if delta.delta:
                    content_parts.append(delta.delta)
                yield message_chunk(
                    trace_id=trace_id,
                    conversation_id=conversation_id,
                    delta=delta.delta,
                    seq=delta.seq,
                )
            if final_usage is None:
                # 上游未回传用量（异常路径）：估算兜底，保证 done 事件完整
                final_usage = TokenUsage.of(
                    prepared.assembled.tokens.total,
                    estimate_tokens("".join(content_parts)),
                )
            steps.append(
                _model_call_step(
                    seq=len(steps),
                    model=prepared.model_code,
                    stream=True,
                    content="".join(content_parts),
                    duration_ms=None,
                    usage=final_usage,
                    status=TraceStatus.OK,
                )
            )
            yield done(
                trace_id=trace_id,
                conversation_id=conversation_id,
                usage=final_usage,
                finish_reason=final_finish,
            )
            got_done = True
        except DomainError as exc:
            failure = exc
            status = TraceStatus.ERROR
            steps.append(
                _model_call_step(
                    seq=len(steps),
                    model=prepared.model_code if prepared else request.model,
                    stream=True,
                    content="".join(content_parts),
                    duration_ms=None,
                    usage=None,
                    status=TraceStatus.ERROR,
                    thought=str(exc),
                )
            )
            yield error(
                trace_id=trace_id,
                conversation_id=conversation_id,
                code=exc.code,
                message=str(exc),
                retriable=exc.retriable,
            )
        except Exception as exc:
            # 非领域异常：标记 error 状态后上抛（500 由框架层处理）
            status = TraceStatus.ERROR
            failure = ModelUnexpected(exc)
            raise
        finally:
            if not got_done and failure is None:
                status = TraceStatus.INTERRUPTED
            await self._persist_stream(
                request=request,
                identity=identity,
                trace_id=trace_id,
                conversation_id=conversation_id,
                question=prepared.question if prepared else "",
                steps=steps,
                content="".join(content_parts),
                usage=final_usage,
                status=status,
                failed=failure is not None,
            )

    # ── 前置链（流式/非流式共用）──────────────────────────────

    async def _prepare(
        self,
        request: ChatRequest,
        *,
        identity: TenantIdentity,
        trace_id: str,
        conversation: Conversation | None = None,
    ) -> _Prepared:
        if conversation is None:
            conversation = await self._ensure_conversation(request, identity)

        profile: AppProfile | None = None
        if request.app_code:
            profile = await self._profiles.get_profile(identity.tenant_id, request.app_code)
            if profile is None:
                raise ConversationNotFoundError(
                    f"应用 {request.app_code!r} 不存在（tenant={identity.tenant_id}）"
                )

        question = self._extract_question(request, profile)
        history = await self._load_history(request, identity, conversation.id, profile)
        knowledge_hits, miss_note = await self._retrieve_knowledge(identity, profile, question)

        assembled = assemble_context(
            AssemblyInput(
                profile=profile,
                history=history,
                knowledge_hits=knowledge_hits,
                question=question,
                variables=request.variables,
                max_tokens_override=request.max_tokens,
                extra_system_notes=(miss_note,) if miss_note else (),
            )
        )

        # 模型解析：应用设定的 modelCode 优先（应用模式），请求 model 兜底（直通）
        model_code = (
            profile.model_code if profile is not None and profile.model_code else request.model
        )
        # 温度/最大 token：请求显式值优先，否则应用设定透传（无硬编码）
        temperature = (
            request.temperature
            if request.temperature is not None
            else (profile.temperature if profile is not None else None)
        )
        max_tokens = (
            request.max_tokens
            if request.max_tokens is not None
            else (profile.max_tokens if profile is not None else None)
        )

        await self._quota.check(identity.tenant_id, estimated_tokens=assembled.tokens.total)

        ctx = InvocationContext(
            tenant_id=identity.tenant_id,
            trace_id=trace_id,
            app_code=request.app_code,
            conversation_id=conversation.id,
        )
        model_request = ChatRequest(
            model=model_code,
            messages=assembled.messages,
            stream=request.stream,
            temperature=temperature,
            max_tokens=max_tokens,
            app_code=request.app_code,
            conversation_id=conversation.id,
        )
        assembly_step = _assembly_step(
            assembled=assembled, app_code=request.app_code, history_count=len(history)
        )
        return _Prepared(
            request=model_request,
            ctx=ctx,
            conversation_id=conversation.id,
            model_code=model_code,
            assembled=assembled,
            assembly_step=assembly_step,
            question=question,
            profile=profile,
        )

    async def _ensure_conversation(
        self, request: ChatRequest, identity: TenantIdentity
    ) -> Conversation:
        if request.conversation_id:
            existing = await asyncio.to_thread(
                self._conversations.get, identity.tenant_id, request.conversation_id
            )
            if existing is None:
                raise ConversationNotFoundError(
                    f"会话 {request.conversation_id!r} 不存在或不属于当前租户"
                )
            return existing
        conversation = Conversation.create(
            tenant_id=identity.tenant_id,
            app_code=request.app_code,
            title="",
        )
        await asyncio.to_thread(self._conversations.create, conversation)
        return conversation

    def _extract_question(self, request: ChatRequest, profile: AppProfile | None) -> str:
        last = request.last_user_message
        if profile is None:
            # 直通模式：messages 原样发送，问题即最后一条 user 内容（落库用）
            return last.content if last is not None else ""
        if last is None:
            raise InvalidRequestError("应用模式请求必须包含至少一条 user 消息")
        return last.content

    async def _load_history(
        self,
        request: ChatRequest,
        identity: TenantIdentity,
        conversation_id: str,
        profile: AppProfile | None,
    ) -> tuple[ChatMessage, ...]:
        if profile is None:
            # 直通模式：历史由调用方随 messages 提供，不查库（OpenAI 兼容语义）
            return ()
        rounds = (
            profile.memory_rounds if profile.memory_rounds is not None else DEFAULT_MEMORY_ROUNDS
        )
        rows = await asyncio.to_thread(
            self._conversations.recent_messages,
            identity.tenant_id,
            conversation_id,
            limit=rounds * 2,
        )
        return tuple(
            ChatMessage(
                role=m.role,
                content=m.content,
                name=m.name,
                tool_call_id=m.tool_call_id,
            )
            for m in rows
        )

    async def _retrieve_knowledge(
        self, identity: TenantIdentity, profile: AppProfile | None, question: str
    ) -> tuple[tuple[KnowledgeHit, ...], str]:
        """知识库检索（本期 Noop：无 knowledge 服务）。

        配了知识库但未命中 → 按 missMessage 生成系统注记，保证"配了知识库的
        应用"在 Phase 0 也有确定行为。
        """
        if profile is None or not profile.knowledge.dataset_ids:
            return (), ""
        hits = await self._knowledge.retrieve(
            tenant_id=identity.tenant_id, policy=profile.knowledge, query=question
        )
        if hits:
            return hits, ""
        return (), profile.knowledge.miss_message or ""

    # ── 落库 ──────────────────────────────────────────────────

    async def _persist_success(
        self, prepared: _Prepared, *, response: ChatResponse, duration_ms: int
    ) -> None:
        await asyncio.to_thread(
            self._append_messages,
            tenant_id=prepared.ctx.tenant_id,
            conversation_id=prepared.conversation_id,
            question=prepared.question,
            content=response.content,
            usage=response.usage,
        )
        trace = ExecutionTrace.create(
            trace_id=prepared.ctx.trace_id,
            tenant_id=prepared.ctx.tenant_id,
            conversation_id=prepared.conversation_id,
            app_code=prepared.request.app_code,
            model=prepared.model_code,
            steps=(
                prepared.assembly_step,
                _model_call_step(
                    seq=1,
                    model=prepared.model_code,
                    stream=False,
                    content=response.content,
                    duration_ms=duration_ms,
                    usage=response.usage,
                    status=TraceStatus.OK,
                ),
            ),
        )
        await asyncio.to_thread(self._traces.add, trace)
        await self._quota.record(prepared.ctx.tenant_id, tokens=response.usage.total_tokens)

    async def _persist_stream(
        self,
        *,
        request: ChatRequest,
        identity: TenantIdentity,
        trace_id: str,
        conversation_id: str,
        question: str,
        steps: list[TraceStep],
        content: str,
        usage: TokenUsage | None,
        status: TraceStatus,
        failed: bool,
    ) -> None:
        """流式终结落库（finally 保证：中断也留痕，可回放）。"""
        if not conversation_id:
            return
        try:
            await asyncio.to_thread(
                self._append_messages,
                tenant_id=identity.tenant_id,
                conversation_id=conversation_id,
                question=question,
                content=content,
                usage=usage,
            )
            trace = ExecutionTrace.create(
                trace_id=trace_id,
                tenant_id=identity.tenant_id,
                conversation_id=conversation_id,
                app_code=request.app_code,
                model=request.model,
                steps=tuple(steps),
                status=status,
            )
            await asyncio.to_thread(self._traces.add, trace)
            if usage is not None and not failed:
                await self._quota.record(identity.tenant_id, tokens=usage.total_tokens)
        except Exception:  # pragma: no cover - 落库失败不掩盖主链路结果
            logger.exception("stream_persist_failed", trace_id=trace_id)

    def _append_messages(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        question: str,
        content: str,
        usage: TokenUsage | None,
    ) -> None:
        """user + assistant 两条消息落库（同步，经 to_thread 调用）。"""
        self._conversations.append_message(
            Message.create(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                role=MessageRole.USER,
                content=question,
                seq=0,
            )
        )
        if content:
            self._conversations.append_message(
                Message.create(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    role=MessageRole.ASSISTANT,
                    content=content,
                    seq=1,
                    usage=usage,
                )
            )


class ModelUnexpected(Exception):
    """非领域异常的包装（finally 里区分"上游错"与"未预期错"）。"""

    def __init__(self, cause: Exception) -> None:
        super().__init__(str(cause))
        self.cause = cause


def _assembly_step(
    *, assembled: AssembledContext, app_code: str | None, history_count: int
) -> TraceStep:
    return TraceStep(
        seq=0,
        kind=TraceStepKind.CONTEXT_ASSEMBLY,
        plugin_name=_ASSEMBLY_PLUGIN_NAME,
        thought=(
            f"装配上下文：app={app_code or '-'}，记忆 {history_count} 条"
            f"（丢弃 {assembled.dropped_history_turns} 轮），"
            f"知识命中 {len(assembled.knowledge_included)} 条"
            f"（跳过 {assembled.knowledge_dropped} 条）"
        ),
        plugin_input={
            "promptBudget": assembled.prompt_budget,
            "tokens": {
                "system": assembled.tokens.system,
                "knowledge": assembled.tokens.knowledge,
                "history": assembled.tokens.history,
                "question": assembled.tokens.question,
                "total": assembled.tokens.total,
            },
        },
        plugin_output={"messages": [m.to_dict() for m in assembled.messages]},
        status=TraceStatus.OK,
    )


def _model_call_step(
    *,
    seq: int,
    model: str,
    stream: bool,
    content: str,
    duration_ms: int | None,
    usage: TokenUsage | None,
    status: TraceStatus,
    thought: str | None = None,
) -> TraceStep:
    output: dict[str, object] = {"content": content}
    if usage is not None:
        output["usage"] = {
            "promptTokens": usage.prompt_tokens,
            "completionTokens": usage.completion_tokens,
            "totalTokens": usage.total_tokens,
            "credits": usage.credits,
        }
    return TraceStep(
        seq=seq,
        kind=TraceStepKind.MODEL_CALL,
        plugin_name=_MODEL_PLUGIN_NAME,
        thought=thought or f"调用模型 {model}",
        plugin_input={"model": model, "stream": stream},
        plugin_output=output,
        duration_ms=duration_ms,
        status=status,
        usage=usage,
    )
