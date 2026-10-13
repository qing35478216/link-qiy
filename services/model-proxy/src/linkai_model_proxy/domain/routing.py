"""路由与调用编排——网关的核心领域服务。

职责：
1. 解析模型 → 查目录 → 展开降级候选链；
2. 逐候选调用适配器，可重试错误才消耗重试次数；
3. **每次尝试都产出计量事件**（成功/失败都发，红线：不准绕过计量）；
4. 终局失败时汇总所有候选的错误抛出。

这是**唯一**持有 `AdapterRegistry` 的地方——api 层拿不到注册表，
物理上杜绝"绕过网关直连适配器"（角色定义铁律）。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from linkai_model_proxy.domain.adapter import ModelAdapter, ProviderCredential
from linkai_model_proxy.domain.errors import (
    CredentialMissingError,
    DomainError,
    ModelCallFailure,
    ModelNotFoundError,
    ProviderCallError,
)
from linkai_model_proxy.domain.fallback import (
    FallbackDecision,
    FallbackPlanner,
    RetryPolicy,
    raise_all_failed,
)
from linkai_model_proxy.domain.invocation import (
    ChatRequest,
    ChatResponse,
    FinishReason,
    StreamDelta,
    TokenUsage,
)
from linkai_model_proxy.domain.metering import (
    CreditCalculator,
    MeteringEvent,
    MeteringOutcome,
    build_event,
)
from linkai_model_proxy.domain.model_card import ModelCard, ProviderId
from linkai_model_proxy.domain.ports import (
    CredentialResolver,
    ModelCatalog,
    TelemetrySink,
    TokenEstimator,
)
from linkai_model_proxy.domain.registry import AdapterRegistry


@dataclass(frozen=True, slots=True)
class InvocationContext:
    """一次调用的横切上下文。"""

    tenant_id: str
    trace_id: str
    app_code: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id 不能为空（铁律 6）")

    @classmethod
    def of(
        cls,
        tenant_id: str,
        *,
        trace_id: str | None = None,
        app_code: str | None = None,
        conversation_id: str | None = None,
    ) -> InvocationContext:
        return cls(
            tenant_id=tenant_id,
            trace_id=trace_id or uuid.uuid4().hex,
            app_code=app_code,
            conversation_id=conversation_id,
        )


class ModelInvocationService:
    """模型调用编排器。"""

    def __init__(
        self,
        *,
        registry: AdapterRegistry,
        catalog: ModelCatalog,
        credentials: CredentialResolver,
        telemetry: TelemetrySink,
        estimator: TokenEstimator,
        planner: FallbackPlanner | None = None,
        credit_calculator: CreditCalculator | None = None,
    ) -> None:
        self._registry = registry
        self._catalog = catalog
        self._credentials = credentials
        self._telemetry = telemetry
        self._estimator = estimator
        self._planner = planner or FallbackPlanner()
        self._credits = credit_calculator or CreditCalculator()

    # ---------- 只读能力：模型列表（供 /v1/models 与 Playground）----------

    def list_models(self, tenant_id: str) -> list[ModelCard]:
        """列出租户可见的模型——过滤掉没有注册适配器的厂商，避免列出调不通的模型。"""
        snapshot = self._catalog.snapshot(tenant_id)
        return [
            card
            for card in snapshot.enabled_models()
            if self._registry.is_registered(card.provider)
        ]

    def describe_model(self, tenant_id: str, code: str) -> ModelCard:
        card = self._catalog.find(tenant_id, code)
        if card is None:
            raise ModelNotFoundError(f"模型 {code!r} 不存在或未对当前租户开放")
        return card

    # ---------- 非流式调用 ----------

    async def complete(self, request: ChatRequest, ctx: InvocationContext) -> ChatResponse:
        """执行一次非流式调用，含降级链与计量。"""
        if request.stream:
            raise DomainError("complete() 不接受 stream=True，请改用 stream()")
        return await self._run_with_fallback(request, ctx)

    # ---------- 流式调用 ----------

    async def stream(
        self, request: ChatRequest, ctx: InvocationContext
    ) -> AsyncIterator[StreamDelta]:
        """执行一次流式调用。

        降级链语义：流式一旦吐出首个分片就不能静默换模型（客户端已见内容），
        因此**只在首个分片产出之前**允许切换；已开始输出后失败只能终止流。
        """
        if not request.stream:
            raise DomainError("stream() 要求 stream=True")

        primary = self._primary_card(request.model, ctx.tenant_id)
        decisions = self._planner.plan(
            primary, lambda code: self._catalog.find(ctx.tenant_id, code)
        )
        errors: list[tuple[str, DomainError]] = []
        seq = 0

        for decision in decisions:
            started = time.monotonic()
            try:
                async for delta in self._stream_once(request, ctx, decision):
                    seq += 1
                    yield delta
            except (ProviderCallError, ModelCallFailure) as exc:
                latency = int((time.monotonic() - started) * 1000)
                # 流式无同模型重试，attempt 恒为 1；已产出的分片数记入失败事件的
                # error 语义之外（下游只需知道"流到一半断了"）
                await self._emit_failure(request, ctx, decision, exc, latency, 1)
                if seq > 0 or not FallbackPlanner.should_fallback(exc):
                    raise
                errors.append((decision.card.code, exc))
                continue
            else:
                # 正常结束（异步迭代器耗尽）——终局计量在 _stream_once 内已发
                return

        raise_all_failed(primary.code, errors)

    # ---------- 内部实现 ----------

    def _primary_card(self, code: str, tenant_id: str) -> ModelCard:
        card = self._catalog.find(tenant_id, code)
        if card is None:
            raise ModelNotFoundError(f"模型 {code!r} 不存在或未对当前租户开放")
        if not card.enabled:
            raise ModelNotFoundError(f"模型 {code!r} 已停用")
        return card

    async def _run_with_fallback(
        self, request: ChatRequest, ctx: InvocationContext
    ) -> ChatResponse:
        primary = self._primary_card(request.model, ctx.tenant_id)
        decisions = self._planner.plan(
            primary, lambda code: self._catalog.find(ctx.tenant_id, code)
        )
        errors: list[tuple[str, DomainError]] = []

        for decision in decisions:
            for attempt in range(1, self._planner.policy.max_attempts + 1):
                started = time.monotonic()
                try:
                    response = await self._complete_once(request, ctx, decision, attempt)
                except (ProviderCallError, CredentialMissingError) as exc:
                    latency = int((time.monotonic() - started) * 1000)
                    await self._emit_failure(request, ctx, decision, exc, latency, attempt)
                    if isinstance(
                        exc, CredentialMissingError
                    ) or not FallbackPlanner.should_fallback(exc):
                        # 凭证缺失/语义错误：换模型也无用，立即失败
                        raise
                    if attempt < self._planner.policy.max_attempts:
                        await self._sleep_backoff(attempt)
                        continue
                    errors.append((decision.card.code, exc))
                    break
                else:
                    return response
            # 当前候选耗尽 → 下一个候选

        # raise_all_failed 内部必定抛出；标注 NoReturn 让类型收敛
        raise_all_failed(primary.code, errors)
        raise AssertionError("unreachable: raise_all_failed 必须抛出")  # pragma: no cover

    async def _complete_once(
        self,
        request: ChatRequest,
        ctx: InvocationContext,
        decision: FallbackDecision,
        attempt: int,
    ) -> ChatResponse:
        card = decision.card
        adapter, credential = await self._resolve_target(request, ctx, card)
        started = time.monotonic()
        response = await adapter.complete(request, card=card, credential=credential)
        latency = int((time.monotonic() - started) * 1000)

        usage = self._finalize_usage(request, response, adapter)
        usage = self._credits.with_credits(card.price, usage)

        await self._telemetry.emit_metering(
            build_event(
                tenant_id=ctx.tenant_id,
                provider=card.provider,
                card=card,
                usage=usage,
                outcome=(
                    MeteringOutcome.SUCCESS
                    if decision.is_primary
                    else MeteringOutcome.FALLBACK_SUCCEEDED
                ),
                latency_ms=latency,
                attempt=attempt,
                trace_id=ctx.trace_id,
                event_id=uuid.uuid4().hex,
                app_code=ctx.app_code or request.app_code,
                conversation_id=ctx.conversation_id or request.conversation_id,
                fallback_from=None if decision.is_primary else self._primary_code(request),
            )
        )
        # 用回填 credits 的 usage 覆盖响应，确保契约 usage.credits 有值
        return _with_usage(response, usage)

    async def _stream_once(
        self,
        request: ChatRequest,
        ctx: InvocationContext,
        decision: FallbackDecision,
    ) -> AsyncIterator[StreamDelta]:
        card = decision.card
        adapter, credential = await self._resolve_target(request, ctx, card)
        started = time.monotonic()
        prompt_tokens = 0
        completion_tokens = 0
        seq = 0
        # 终局分片**先扣住不yield**：credits 要等计量算完才能填，
        # 否则客户端会收到 usage.credits=0 的 done 事件（少算账）。
        terminal: StreamDelta | None = None

        async for delta in adapter.stream(request, card=card, credential=credential):
            if delta.usage is not None:
                prompt_tokens = delta.usage.prompt_tokens or prompt_tokens
                completion_tokens = delta.usage.completion_tokens or completion_tokens
            if delta.is_terminal:
                terminal = delta
                continue
            seq += 1
            yield delta

        if prompt_tokens == 0 and completion_tokens == 0:
            # 厂商未回 usage → 估算兜底，计量不能缺数
            est_prompt, est_completion = self._estimator.estimate(request, "")
            prompt_tokens, completion_tokens = est_prompt, est_completion

        usage = self._credits.with_credits(
            card.price, TokenUsage.of(prompt_tokens, completion_tokens)
        )

        # 终局分片：厂商给的就用其 finish_reason，没给则补一个 stop
        # （保证消费端总能收到 done 事件，不必依赖连接关闭）
        yield StreamDelta(
            delta=terminal.delta if terminal is not None else "",
            seq=seq + 1,
            finish_reason=(terminal.finish_reason if terminal is not None else FinishReason.STOP)
            or FinishReason.STOP,
            usage=usage,
        )

        latency = int((time.monotonic() - started) * 1000)
        await self._telemetry.emit_metering(
            build_event(
                tenant_id=ctx.tenant_id,
                provider=card.provider,
                card=card,
                usage=usage,
                outcome=(
                    MeteringOutcome.SUCCESS
                    if decision.is_primary
                    else MeteringOutcome.FALLBACK_SUCCEEDED
                ),
                latency_ms=latency,
                attempt=1,
                trace_id=ctx.trace_id,
                event_id=uuid.uuid4().hex,
                app_code=ctx.app_code or request.app_code,
                conversation_id=ctx.conversation_id or request.conversation_id,
                fallback_from=None if decision.is_primary else self._primary_code(request),
            )
        )

    async def _resolve_target(
        self, request: ChatRequest, ctx: InvocationContext, card: ModelCard
    ) -> tuple[ModelAdapter, ProviderCredential]:
        """取适配器 + 凭证。凭证缺失时抛不可降级错误。"""
        # 未注册适配器属于部署配置错误，应当快速失败而不是切备选
        adapter = self._registry.resolve(card.provider)
        credential = await self._credentials.resolve(ctx.tenant_id, card, request=request)
        if credential is None:
            raise CredentialMissingError(
                f"厂商 {card.provider!r} 无可用凭证"
                f"（租户 {ctx.tenant_id} 未配置平台 Key 或自带 Key）"
            )
        return adapter, credential

    def _finalize_usage(
        self, request: ChatRequest, response: ChatResponse, adapter: ModelAdapter
    ) -> TokenUsage:
        """厂商未给usage 时用估算器补齐。"""
        if response.usage.total_tokens > 0:
            return response.usage
        est_prompt, est_completion = self._estimator.estimate(request, response.content)
        return TokenUsage.of(est_prompt, est_completion)

    @staticmethod
    def _primary_code(request: ChatRequest) -> str:
        return request.model

    async def _emit_failure(
        self,
        request: ChatRequest,
        ctx: InvocationContext,
        decision: FallbackDecision,
        exc: DomainError,
        latency_ms: int,
        attempt: int,
    ) -> None:
        """失败也发计量事件——失败尝试不计费，但对账与厂商成本核算需要它。"""
        await self._telemetry.emit_metering(
            build_event(
                tenant_id=ctx.tenant_id,
                provider=decision.card.provider,
                card=decision.card,
                usage=TokenUsage.of(0, 0),
                outcome=MeteringOutcome.FAILED,
                latency_ms=latency_ms,
                attempt=attempt,
                trace_id=ctx.trace_id,
                event_id=uuid.uuid4().hex,
                app_code=ctx.app_code or request.app_code,
                conversation_id=ctx.conversation_id or request.conversation_id,
                error_code=exc.code,
                fallback_from=None if decision.is_primary else self._primary_code(request),
            )
        )

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        delay = RetryPolicy(backoff_base_ms=200).delay_ms(attempt)
        if delay > 0:
            await asyncio.sleep(delay / 1000)


def _with_usage(response: ChatResponse, usage: TokenUsage) -> ChatResponse:
    """返回带新 usage 的响应副本（ChatResponse 不可变）。"""
    return ChatResponse(
        id=response.id,
        created=response.created,
        model=response.model,
        choices=response.choices,
        usage=usage,
    )


__all__ = [
    "InvocationContext",
    "MeteringEvent",
    "ModelInvocationService",
    "ProviderId",
]
