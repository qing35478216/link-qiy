"""计量埋点用例——验收标准 4与 6。

验收标准 4：每次调用产出 MeteringEvent，**事件字段有契约测试**。
验收标准 6：不准绕过计量直接调模型——由"每次尝试都有事件"断言保证。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from linkai_model_proxy.domain.errors import ModelCallFailure, ProviderCallError
from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatRequest,
    MessageRole,
    TokenUsage,
)
from linkai_model_proxy.domain.metering import (
    CreditCalculator,
    MeteringEvent,
    MeteringOutcome,
    build_event,
)
from linkai_model_proxy.domain.model_card import ModelPrice
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.domain.routing import InvocationContext, ModelInvocationService
from linkai_model_proxy.infra.memory import (
    HeuristicTokenEstimator,
    InMemoryCredentialStore,
    InMemoryModelCatalog,
    InMemoryTelemetrySink,
)

from tests.conftest import (
    TENANT,
    ScriptedAdapter,
    ScriptedAdapterFactory,
    make_card,
    make_request,
    make_response,
)

CARD = make_card(code="billing-model", provider="vendor-a", price=ModelPrice(1.0, 2.0))


class TestCreditCalculator:
    def test_basic_token_pricing(self) -> None:
        calc = CreditCalculator()
        # 1000/1000 * 1.0 + 500/1000 * 2.0 = 1.0 + 1.0 = 2
        credits = calc.compute(
            ModelPrice(input_per_1k=1.0, output_per_1k=2.0), TokenUsage.of(1000, 500)
        )
        assert credits == 2

    def test_credit_per_call_added(self) -> None:
        calc = CreditCalculator()
        price = ModelPrice(input_per_1k=0, output_per_1k=0, credit_per_call=1)
        assert calc.compute(price, TokenUsage.of(10, 10)) == 1

    def test_rounds_up(self) -> None:
        """不足 1 积分按 1 算——避免免费调用被当作 0 积分而漏计。"""
        calc = CreditCalculator()
        price = ModelPrice(input_per_1k=0.0001, output_per_1k=0)
        # 1/1000 * 0.0001 = 1e-7 -> ceiling 1（极低单价也不得为0）
        assert calc.compute(price, TokenUsage.of(1, 1)) == 1

    def test_decimal_precision_no_float_drift(self) -> None:
        """0.1 这类价格不能出现浮点误差导致的账单抖动。"""
        calc = CreditCalculator()
        price = ModelPrice(input_per_1k=0.1, output_per_1k=0.1)
        # 7000 prompt + 3000 completion = 0.7 + 0.3 = 1.0
        assert calc.compute(price, TokenUsage.of(7000, 3000)) == 1

    def test_free_model_zero_credits(self) -> None:
        calc = CreditCalculator()
        assert calc.compute(ModelPrice(0, 0), TokenUsage.of(1000, 1000)) == 0

    def test_with_credits_returns_new_instance(self) -> None:
        """TokenUsage 不可变——回填 credits 不污染原对象。"""
        calc = CreditCalculator()
        original = TokenUsage.of(1000, 1000)
        updated = calc.with_credits(ModelPrice(1.0, 1.0), original)
        assert updated is not original
        assert original.credits == 0
        # 1000/1000*1.0 + 1000/1000*1.0 = 2
        assert updated.credits == 2

    def test_with_credits_idempotent(self) -> None:
        calc = CreditCalculator()
        usage = TokenUsage.of(100, 100)
        once = calc.with_credits(ModelPrice(1.0, 1.0), usage)
        twice = calc.with_credits(ModelPrice(1.0, 1.0), once)
        assert once is twice


class TestMeteringEventContract:
    """契约测试：事件字段与下游 T-007 消费方对齐。"""

    def test_required_fields_present(self) -> None:
        event = build_event(
            tenant_id=TENANT,
            provider="openai",
            card=CARD,
            usage=TokenUsage.of(100, 50, ),
            outcome=MeteringOutcome.SUCCESS,
            latency_ms=120,
            attempt=1,
            trace_id="trace-1",
            event_id="evt-1",
            app_code="app-x",
            conversation_id="conv-1",
        )
        payload = event.to_payload()
        for field in (
            "event_id",
            "tenant_id",
            "app_code",
            "conversation_id",
            "trace_id",
            "provider",
            "model_code",
            "outcome",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "credits",
            "latency_ms",
            "attempt",
            "occurred_at",
            "error_code",
            "fallback_from",
        ):
            assert field in payload, f"计量事件缺字段 {field}"

    def test_payload_values_are_json_scalar(self) -> None:
        """跨语言友好：payload 只含标量（Go/Python 都能直接反序列化）。"""
        event = build_event(
            tenant_id=TENANT,
            provider="openai",
            card=CARD,
            usage=TokenUsage.of(10, 5),
            outcome=MeteringOutcome.SUCCESS,
            latency_ms=1,
            attempt=1,
            trace_id="t",
            event_id="e",
        )
        for key, value in event.to_payload().items():
            assert value is None or isinstance(value, (str, int, float, bool)), key

    def test_occurred_at_is_iso8601_utc(self) -> None:
        event = build_event(
            tenant_id=TENANT,
            provider="openai",
            card=CARD,
            usage=TokenUsage.of(1, 1),
            outcome=MeteringOutcome.SUCCESS,
            latency_ms=1,
            attempt=1,
            trace_id="t",
            event_id="e",
        )
        parsed = datetime.fromisoformat(event.to_payload()["occurred_at"])  # type: ignore[arg-type]
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_tenant_id_required(self) -> None:
        """铁律 6：没有租户的用量无法归属钱包——必须拒绝构造。"""
        with pytest.raises(ValueError, match="tenant_id"):
            MeteringEvent(
                event_id="e",
                tenant_id="",
                app_code=None,
                conversation_id=None,
                trace_id="t",
                provider="openai",
                model_code="m",
                outcome=MeteringOutcome.SUCCESS,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                credits=0,
                latency_ms=0,
                attempt=1,
                occurred_at=datetime.now(UTC),
            )

    def test_attempt_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="attempt"):
            build_event(
                tenant_id=TENANT,
                provider="openai",
                card=CARD,
                usage=TokenUsage.of(1, 1),
                outcome=MeteringOutcome.SUCCESS,
                latency_ms=1,
                attempt=0,
                trace_id="t",
                event_id="e",
            )

    def test_failed_outcome_has_zero_credits(self) -> None:
        """失败尝试不计费。"""
        event = build_event(
            tenant_id=TENANT,
            provider="openai",
            card=CARD,
            usage=TokenUsage(1, 1, 2, credits=99),
            outcome=MeteringOutcome.FAILED,
            latency_ms=1,
            attempt=1,
            trace_id="t",
            event_id="e",
        )
        assert event.credits == 0
        assert event.is_billable is False


class TestMeteringIsUnbypassable:
    """验收标准 6：每次调用都有计量——漏发即测试失败。"""

    async def test_every_successful_call_emits_exactly_one_event(self) -> None:
        telemetry = InMemoryTelemetrySink()
        service = _service(telemetry)
        await service.complete(
            make_request("billing-model"), InvocationContext(tenant_id=TENANT, trace_id="m1")
        )
        assert len(telemetry.events) == 1
        event = telemetry.events[0]
        assert event.model_code == "billing-model"
        assert event.provider == "vendor-a"
        assert event.prompt_tokens == 100
        assert event.completion_tokens == 50
        # 100/1000*1.0 + 50/1000*2.0 = 0.1 + 0.1 = 0.2 -> ceiling 1
        assert event.credits == 1

    async def test_credits_backfilled_into_response(self) -> None:
        """契约 usage.credits 必须有值——客户端要展示消耗。"""
        telemetry = InMemoryTelemetrySink()
        service = _service(telemetry)
        response = await service.complete(
            make_request("billing-model"), InvocationContext(tenant_id=TENANT, trace_id="m2")
        )
        assert response.usage.credits == telemetry.events[0].credits
        assert response.usage.total_tokens == 150

    async def test_failed_call_still_emits_event(self) -> None:
        telemetry = InMemoryTelemetrySink()
        registry = AdapterRegistry()
        registry.register(
            "vendor-a",
            ScriptedAdapterFactory(
                ScriptedAdapter("vendor-a", error=ProviderCallError("503"))
            ),
        )
        service = _service(telemetry, registry=registry)
        with pytest.raises(ModelCallFailure):
            await service.complete(
                make_request("billing-model"), InvocationContext(tenant_id=TENANT, trace_id="m3")
            )
        assert len(telemetry.events) == 1
        assert telemetry.events[0].outcome is MeteringOutcome.FAILED
        assert telemetry.events[0].error_code == "PROVIDER_CALL_FAILED"

    async def test_events_carry_tenant_and_trace(self) -> None:
        telemetry = InMemoryTelemetrySink()
        service = _service(telemetry)
        await service.complete(
            make_request("billing-model"),
            InvocationContext(tenant_id=TENANT, trace_id="trace-abc", app_code="app-1"),
        )
        event = telemetry.events[0]
        assert event.tenant_id == TENANT
        assert event.trace_id == "trace-abc"
        assert event.app_code == "app-1"

    async def test_tenant_isolation_in_metering(self) -> None:
        """两个租户的用量必须分得开（铁律 6）。"""
        telemetry = InMemoryTelemetrySink()
        service = _service(telemetry)
        for tenant in (TENANT, "tenant-other"):
            await service.complete(
                make_request("billing-model"), InvocationContext(tenant_id=tenant, trace_id="t")
            )
        assert len(telemetry.for_tenant(TENANT)) == 1
        assert len(telemetry.for_tenant("tenant-other")) == 1

    async def test_usage_missing_falls_back_to_estimator(self) -> None:
        """厂商不回 usage 时用估算器补齐——计量不能缺数。"""
        telemetry = InMemoryTelemetrySink()
        response = make_response("内容很长的一段回答文本", prompt_tokens=0, completion_tokens=0)
        registry = AdapterRegistry()
        registry.register("vendor-a", ScriptedAdapterFactory(ScriptedAdapter("vendor-a", response=response)))
        service = _service(telemetry, registry=registry)
        result = await service.complete(
            make_request("billing-model"), InvocationContext(tenant_id=TENANT, trace_id="m4")
        )
        assert result.usage.prompt_tokens > 0
        assert result.usage.completion_tokens > 0
        assert telemetry.events[0].total_tokens > 0


def _service(
    telemetry: InMemoryTelemetrySink,
    *,
    registry: AdapterRegistry | None = None,
) -> ModelInvocationService:
    reg = registry or AdapterRegistry()
    if registry is None:
        reg.register(
            "vendor-a",
            ScriptedAdapterFactory(
                ScriptedAdapter("vendor-a", response=make_response("回答"))
            ),
        )
    return ModelInvocationService(
        registry=reg,
        catalog=InMemoryModelCatalog(public_models={CARD.code: CARD}),
        credentials=InMemoryCredentialStore(platform_keys={"vendor-a": "sk-vendor-a"}),
        telemetry=telemetry,
        estimator=HeuristicTokenEstimator(),
    )


class TestTokenEstimator:
    def test_cjk_weighted_heavier_than_ascii(self) -> None:
        """中文按 4 字符/token 会严重低估——必须按字计。"""
        est = HeuristicTokenEstimator()
        ascii_req = ChatRequest(
            model="m", messages=(ChatMessage(role=MessageRole.USER, content="a" * 40),)
        )
        cjk_req = ChatRequest(
            model="m", messages=(ChatMessage(role=MessageRole.USER, content="字" * 40),)
        )
        ascii_tokens, _ = est.estimate(ascii_req, "")
        cjk_tokens, _ = est.estimate(cjk_req, "")
        assert cjk_tokens > ascii_tokens

    def test_empty_response_still_returns_positive(self) -> None:
        est = HeuristicTokenEstimator()
        prompt, completion = est.estimate(make_request("m"), "")
        assert prompt >= 1
        assert completion >= 1

    def test_message_overhead_counted(self) -> None:
        est = HeuristicTokenEstimator()
        one = est.estimate(
            ChatRequest(model="m", messages=(ChatMessage(role=MessageRole.USER, content="hi"),)),
            "",
        )
        two = est.estimate(
            ChatRequest(
                model="m",
                messages=(
                    ChatMessage(role=MessageRole.USER, content="hi"),
                    ChatMessage(role=MessageRole.ASSISTANT, content="ok"),
                ),
            ),
            "",
        )
        assert two[0] > one[0]


class TestDecimalUsage:
    def test_calculator_scale_is_fine_grained(self) -> None:
        """价格极低的模型（如 GLM Flash）也不应全部折成 0。"""
        calc = CreditCalculator()
        price = ModelPrice(input_per_1k=0.0001, output_per_1k=0.0001)
        usage = TokenUsage.of(1000, 1000)
        assert calc.compute(price, usage) == 1
        # 噪声精度必须远细于计费粒度（1e-6 会把 1e-7 的消耗截成 0）
        assert calc._scale == Decimal("0.000000001")
