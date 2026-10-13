"""降级链用例——验收标准 3：**主模型失败自动切备选**。"""

from __future__ import annotations

import pytest

from linkai_model_proxy.domain.errors import (
    CredentialMissingError,
    DomainError,
    ModelCallFailure,
    ModelNotFoundError,
    ProviderCallError,
    ProviderRateLimitedError,
)
from linkai_model_proxy.domain.fallback import FallbackPlanner, RetryPolicy
from linkai_model_proxy.domain.invocation import ChatMessage, ChatRequest, MessageRole
from linkai_model_proxy.domain.metering import MeteringOutcome
from linkai_model_proxy.domain.model_card import ModelCard, ModelPrice
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.domain.routing import InvocationContext, ModelInvocationService
from linkai_model_proxy.infra.memory import (
    HeuristicTokenEstimator,
    InMemoryCredentialStore,
    InMemoryModelCatalog,
    InMemoryTelemetrySink,
)

from tests.conftest import (
    OTHER_TENANT,
    TENANT,
    ScriptedAdapter,
    ScriptedAdapterFactory,
    make_card,
    make_request,
    make_response,
)

PRIMARY = make_card(code="primary-model", provider="vendor-a")
FALLBACK_1 = make_card(code="fallback-1", provider="vendor-b")
FALLBACK_2 = make_card(code="fallback-2", provider="vendor-c")
PRIMARY_WITH_CHAIN = ModelCard(
    code="primary-model",
    name="PRIMARY",
    provider="vendor-a",
    capabilities=PRIMARY.capabilities,
    price=ModelPrice(input_per_1k=1.0, output_per_1k=2.0),
    fallback_codes=("fallback-1", "fallback-2"),
)


def build_service(
    *,
    cards: dict[str, ModelCard],
    adapters: dict[str, ScriptedAdapter],
    policy: RetryPolicy | None = None,
    telemetry: InMemoryTelemetrySink | None = None,
    credentials: InMemoryCredentialStore | None = None,
) -> tuple[ModelInvocationService, InMemoryTelemetrySink]:
    """组装一个带脚本化适配器的调用服务。"""
    registry = AdapterRegistry()
    for provider, adapter in adapters.items():
        registry.register(provider, ScriptedAdapterFactory(adapter))

    catalog = InMemoryModelCatalog(public_models=cards)
    sink = telemetry or InMemoryTelemetrySink()
    creds = credentials or InMemoryCredentialStore(
        platform_keys={p: f"sk-{p}" for p in adapters}
    )
    service = ModelInvocationService(
        registry=registry,
        catalog=catalog,
        credentials=creds,
        telemetry=sink,
        estimator=HeuristicTokenEstimator(),
        planner=FallbackPlanner(policy=policy or RetryPolicy(max_attempts=1)),
    )
    return service, sink


class TestFallbackPlanner:
    def test_plan_orders_primary_first(self) -> None:
        planner = FallbackPlanner()
        decisions = planner.plan(PRIMARY_WITH_CHAIN, lambda code: None)
        assert len(decisions) == 1
        assert decisions[0].is_primary

    def test_plan_appends_resolvable_fallbacks(self) -> None:
        cards = {c.code: c for c in (PRIMARY_WITH_CHAIN, FALLBACK_1, FALLBACK_2)}
        planner = FallbackPlanner()
        decisions = planner.plan(PRIMARY_WITH_CHAIN, cards.get)
        assert [d.card.code for d in decisions] == ["primary-model", "fallback-1", "fallback-2"]
        assert [d.is_primary for d in decisions] == [True, False, False]
        assert decisions[1].attempt_label == "fallback#1"

    def test_unresolvable_fallback_skipped(self) -> None:
        cards = {PRIMARY_WITH_CHAIN.code: PRIMARY_WITH_CHAIN, FALLBACK_2.code: FALLBACK_2}
        planner = FallbackPlanner()
        decisions = planner.plan(PRIMARY_WITH_CHAIN, cards.get)
        assert [d.card.code for d in decisions] == ["primary-model", "fallback-2"]

    def test_disabled_fallback_skipped(self) -> None:
        disabled = ModelCard(
            code="fallback-1", name="X", provider="vendor-b", capabilities=(), enabled=False
        )
        cards = {PRIMARY_WITH_CHAIN.code: PRIMARY_WITH_CHAIN, "fallback-1": disabled}
        planner = FallbackPlanner()
        assert len(planner.plan(PRIMARY_WITH_CHAIN, cards.get)) == 1

    def test_cyclic_config_does_not_loop_forever(self) -> None:
        """降级配置成环时必须终止（防无限降级）。"""
        cyclic = ModelCard(
            code="a", name="A", provider="p", capabilities=(), fallback_codes=("b", "a")
        )
        other = ModelCard(code="b", name="B", provider="p", capabilities=(), fallback_codes=("a",))
        cards = {"a": cyclic, "b": other}
        decisions = FallbackPlanner().plan(cyclic, cards.get)
        assert [d.card.code for d in decisions] == ["a", "b"]

    def test_policy_can_disable_fallback(self) -> None:
        cards = {"fallback-1": FALLBACK_1}
        planner = FallbackPlanner(policy=RetryPolicy(honor_fallback_chain=False))
        assert len(planner.plan(PRIMARY_WITH_CHAIN, cards.get)) == 1

    def test_should_fallback_only_for_retriable(self) -> None:
        assert FallbackPlanner.should_fallback(ProviderCallError("boom")) is True
        assert FallbackPlanner.should_fallback(ProviderRateLimitedError("429")) is True
        assert FallbackPlanner.should_fallback(CredentialMissingError("no key")) is False
        assert FallbackPlanner.should_fallback(ModelNotFoundError("no model")) is False


class TestFallbackExecution:
    async def test_primary_success_uses_no_fallback(self) -> None:
        service, telemetry = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={
                "vendor-a": ScriptedAdapter("vendor-a", response=make_response("主模型回答")),
                "vendor-b": ScriptedAdapter("vendor-b", response=make_response("备选回答")),
            },
        )
        response = await service.complete(
            make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t1")
        )
        assert response.content == "主模型回答"
        assert len(telemetry.events) == 1
        assert telemetry.events[0].outcome is MeteringOutcome.SUCCESS

    async def test_falls_back_when_primary_unavailable(self) -> None:
        primary = ScriptedAdapter(
            "vendor-a", error=ProviderCallError("503 service unavailable")
        )
        backup = ScriptedAdapter("vendor-b", response=make_response("备选成功"))
        service, telemetry = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={"vendor-a": primary, "vendor-b": backup},
        )
        response = await service.complete(
            make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t2")
        )
        assert response.content == "备选成功"
        assert primary.calls == ["primary-model"]
        assert backup.calls == ["fallback-1"]

        # 失败尝试 + 成功尝试各一个计量事件
        assert len(telemetry.events) == 2
        failed, succeeded = telemetry.events
        assert failed.outcome is MeteringOutcome.FAILED
        assert failed.model_code == "primary-model"
        assert failed.credits == 0
        assert succeeded.outcome is MeteringOutcome.FALLBACK_SUCCEEDED
        assert succeeded.model_code == "fallback-1"
        assert succeeded.fallback_from == "primary-model"

    async def test_cascades_through_two_fallbacks(self) -> None:
        service, telemetry = build_service(
            cards={
                "primary-model": PRIMARY_WITH_CHAIN,
                "fallback-1": FALLBACK_1,
                "fallback-2": FALLBACK_2,
            },
            adapters={
                "vendor-a": ScriptedAdapter("vendor-a", error=ProviderCallError("503")),
                "vendor-b": ScriptedAdapter("vendor-b", error=ProviderRateLimitedError("429")),
                "vendor-c": ScriptedAdapter("vendor-c", response=make_response("三级成功")),
            },
        )
        response = await service.complete(
            make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t3")
        )
        assert response.content == "三级成功"
        assert len(telemetry.events) == 3
        assert [e.outcome for e in telemetry.events] == [
            MeteringOutcome.FAILED,
            MeteringOutcome.FAILED,
            MeteringOutcome.FALLBACK_SUCCEEDED,
        ]

    async def test_all_candidates_failed_raises_terminal(self) -> None:
        service, telemetry = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={
                "vendor-a": ScriptedAdapter("vendor-a", error=ProviderCallError("503")),
                "vendor-b": ScriptedAdapter("vendor-b", error=ProviderCallError("503")),
            },
        )
        with pytest.raises(ModelCallFailure) as exc:
            await service.complete(
                make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t4")
            )
        assert "全部候选失败" in str(exc.value)
        # 失败也发计量——对账需要
        assert len(telemetry.events) == 2
        assert all(e.outcome is MeteringOutcome.FAILED for e in telemetry.events)

    async def test_non_retriable_error_does_not_fall_back(self) -> None:
        """4xx 语义错误不降级——避免无谓的模型切换与计费。"""
        primary = ScriptedAdapter(
            "vendor-a", error=ProviderCallError("400 bad model", retriable=False)
        )
        backup = ScriptedAdapter("vendor-b", response=make_response("不该被调用"))
        service, _ = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={"vendor-a": primary, "vendor-b": backup},
        )
        with pytest.raises(ProviderCallError):
            await service.complete(
                make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t5")
            )
        assert primary.calls == ["primary-model"]
        assert backup.calls == []  # 备选从未被调用

    async def test_missing_credential_fails_fast(self) -> None:
        """凭证缺失属部署问题，不该切模型空转。"""
        primary = ScriptedAdapter("vendor-a", response=make_response("x"))
        backup = ScriptedAdapter("vendor-b", response=make_response("y"))
        service, _ = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={"vendor-a": primary, "vendor-b": backup},
            credentials=InMemoryCredentialStore(platform_keys={}),  # 无任何凭证
        )
        with pytest.raises(CredentialMissingError):
            await service.complete(
                make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t6")
            )
        assert backup.calls == []

    async def test_retry_before_fallback(self) -> None:
        """同模型重试耗尽后才降级。"""
        flaky = ScriptedAdapter("vendor-a", error=ProviderCallError("503"))
        backup = ScriptedAdapter("vendor-b", response=make_response("重试后仍失败才降级"))
        service, telemetry = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={"vendor-a": flaky, "vendor-b": backup},
            policy=RetryPolicy(max_attempts=3, backoff_base_ms=0),
        )
        response = await service.complete(
            make_request("primary-model"), InvocationContext(tenant_id=TENANT, trace_id="t7")
        )
        assert response.content == "重试后仍失败才降级"
        assert flaky.calls == ["primary-model"] * 3
        assert len(telemetry.events) == 4  # 3 次失败 + 1 次降级成功


class TestStreamFallback:
    async def test_stream_falls_back_before_first_chunk(self) -> None:
        """首个分片产出前允许降级。"""
        primary = ScriptedAdapter("vendor-a", error=ProviderCallError("503"))
        backup = ScriptedAdapter("vendor-b", chunks=("备", "选"), chunk_usage=None)
        service, telemetry = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={"vendor-a": primary, "vendor-b": backup},
        )
        request = ChatRequest(
            model="primary-model",
            messages=(ChatMessage(role=MessageRole.USER, content="hi"),),
            stream=True,
        )
        deltas = [d async for d in service.stream(request, InvocationContext(tenant_id=TENANT, trace_id="s1"))]
        assert [d.delta for d in deltas] == ["备", "选"]
        assert primary.calls == ["primary-model"]
        assert backup.calls == ["fallback-1"]
        assert len(telemetry.events) == 2

    async def test_stream_does_not_switch_after_output_started(self) -> None:
        """已开始输出后失败不能静默换模型（客户端已见内容）。"""

        class MidStreamFail(ScriptedAdapter):
            async def stream(self, request, *, card, credential):  # type: ignore[no-untyped-def]
                self.calls.append(card.code)
                from linkai_model_proxy.domain.invocation import StreamDelta

                yield StreamDelta(delta="半句", seq=0)
                raise ProviderCallError("连接中断")

        primary = MidStreamFail("vendor-a")
        backup = ScriptedAdapter("vendor-b", chunks=("不该出现",))
        service, _ = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN, "fallback-1": FALLBACK_1},
            adapters={"vendor-a": primary, "vendor-b": backup},
        )
        request = ChatRequest(
            model="primary-model",
            messages=(ChatMessage(role=MessageRole.USER, content="hi"),),
            stream=True,
        )
        received = []
        with pytest.raises(ProviderCallError):
            async for delta in service.stream(
                request, InvocationContext(tenant_id=TENANT, trace_id="s2")
            ):
                received.append(delta)
        assert [d.delta for d in received] == ["半句"]
        assert backup.calls == []  # 已吐内容，不允许切备选


class TestRoutingGuards:
    async def test_unknown_model_raises(self) -> None:
        service, telemetry = build_service(cards={}, adapters={})
        with pytest.raises(ModelNotFoundError):
            await service.complete(
                make_request("nope"), InvocationContext(tenant_id=TENANT, trace_id="g1")
            )
        assert telemetry.events == []  # 模型不存在没发生调用，不该计量

    async def test_disabled_model_raises(self) -> None:
        disabled = ModelCard(
            code="off", name="OFF", provider="vendor-a", capabilities=(), enabled=False
        )
        service, _ = build_service(
            cards={"off": disabled}, adapters={"vendor-a": ScriptedAdapter("vendor-a")}
        )
        with pytest.raises(ModelNotFoundError, match="停用"):
            await service.complete(
                make_request("off"), InvocationContext(tenant_id=TENANT, trace_id="g2")
            )

    async def test_tenant_private_model_isolated(self) -> None:
        """铁律 6：租户私有模型只对该租户可见。"""
        private = make_card(code="my-model", provider="vendor-a")
        catalog = InMemoryModelCatalog(public_models={})
        catalog.add_tenant_model(TENANT, private)
        registry = AdapterRegistry()
        registry.register("vendor-a", ScriptedAdapterFactory(ScriptedAdapter("vendor-a")))
        service = ModelInvocationService(
            registry=registry,
            catalog=catalog,
            credentials=InMemoryCredentialStore(platform_keys={"vendor-a": "sk"}),
            telemetry=InMemoryTelemetrySink(),
            estimator=HeuristicTokenEstimator(),
        )
        with pytest.raises(ModelNotFoundError):
            await service.complete(
                make_request("my-model"),
                InvocationContext(tenant_id=OTHER_TENANT, trace_id="g3"),
            )

    async def test_list_models_filters_unregistered_providers(self) -> None:
        service, _ = build_service(
            cards={"primary-model": PRIMARY_WITH_CHAIN},
            adapters={"vendor-a": ScriptedAdapter("vendor-a")},
        )
        codes = [card.code for card in service.list_models(TENANT)]
        assert "primary-model" in codes
        # fallback-1 厂商 vendor-b 未注册，不应出现在可调用列表
        assert "fallback-1" not in codes

    def test_empty_tenant_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            InvocationContext(tenant_id="", trace_id="x")


class TestDomainErrorHierarchy:
    def test_all_errors_are_domain_errors(self) -> None:
        for exc in (
            ModelNotFoundError("x"),
            ProviderCallError("x"),
            ProviderRateLimitedError("x"),
            CredentialMissingError("x"),
            ModelCallFailure("x"),
        ):
            assert isinstance(exc, DomainError)
            assert exc.code
