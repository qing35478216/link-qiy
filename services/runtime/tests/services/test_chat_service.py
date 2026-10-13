"""ChatService 编排用例（脚本化端口）。

覆盖：非流式成功链路、流式事件序列与落库、配额 429、上游错误 →
error 事件、会话续聊租户校验、执行链 steps 落库内容。
"""

from __future__ import annotations

from linkai_runtime.domain.chat import ChatRequest, MessageRole
from linkai_runtime.domain.errors import ModelUpstreamError, QuotaExceededError
from linkai_runtime.domain.ports import TenantIdentity
from linkai_runtime.infra.conversation_repo import SqlAlchemyConversationRepository
from linkai_runtime.infra.quota_guard import InMemoryQuotaGuard
from linkai_runtime.infra.trace_repo import SqlAlchemyExecutionTraceRepository
from tests.conftest import (
    DEMO_APP_CONFIG,
    TENANT,
    ScriptedGateway,
    make_chat_service,
)

IDENTITY = TenantIdentity(tenant_id=TENANT, user_id="u-001", key_id="k-001")


def _chat_request(**overrides: object) -> ChatRequest:
    from linkai_runtime.domain.chat import ChatMessage

    base: dict[str, object] = {
        "model": "deepseek-chat",
        "messages": (ChatMessage(role=MessageRole.USER, content="今天天气怎么样？"),),
        "stream": False,
    }
    base.update(overrides)
    return ChatRequest(**base)  # type: ignore[arg-type]


class TestNonStreaming:
    async def test_complete_returns_response_and_persists(self) -> None:
        gateway = ScriptedGateway(chunks=("你好", "世界"))
        service, factory = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        outcome = await service.complete(
            _chat_request(app_code="demo"), identity=IDENTITY, trace_id="trace-001"
        )
        assert outcome.response.content == "你好世界"
        assert outcome.response.usage.credits == 7
        assert outcome.conversation_id
        # 落库：user + assistant 两条消息
        repo = SqlAlchemyConversationRepository(factory)
        messages = repo.recent_messages(TENANT, outcome.conversation_id, limit=10)
        assert [m.role for m in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
        assert messages[1].content == "你好世界"
        assert messages[1].usage is not None and messages[1].usage.credits == 7
        # 落库：执行链两步
        trace_repo = SqlAlchemyExecutionTraceRepository(factory)
        snapshot = trace_repo.snapshot(TENANT, "trace-001")
        assert snapshot is not None
        steps = snapshot["steps"]
        assert isinstance(steps, list) and len(steps) == 2
        assert steps[0]["kind"] == "context_assembly"  # type: ignore[index]
        assert steps[1]["kind"] == "model_call"  # type: ignore[index]
        assert steps[1]["pluginName"] == "model-proxy"  # type: ignore[index]

    async def test_app_profile_model_overrides_request_model(self) -> None:
        gateway = ScriptedGateway()
        service, _ = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        await service.complete(
            _chat_request(model="gpt-4o-mini", app_code="demo"),
            identity=IDENTITY,
            trace_id="trace-002",
        )
        _kind, request, ctx = gateway.calls[0]
        assert request.model == "deepseek-chat"  # 应用设定的 modelCode 优先
        assert ctx.tenant_id == TENANT
        assert ctx.trace_id == "trace-002"

    async def test_quota_exceeded_raises(self) -> None:
        gateway = ScriptedGateway()
        quota = InMemoryQuotaGuard(default_daily_tokens=10)
        service, _ = make_chat_service(
            gateway=gateway, profiles={"demo": DEMO_APP_CONFIG}, quota=quota
        )
        import pytest

        with pytest.raises(QuotaExceededError) as exc_info:
            await service.complete(
                _chat_request(app_code="demo"), identity=IDENTITY, trace_id="trace-003"
            )
        assert exc_info.value.client_status == 429
        assert not gateway.calls  # 配额拦截在模型调用之前

    async def test_upstream_error_propagates(self) -> None:
        gateway = ScriptedGateway(error=ModelUpstreamError("上游 503", retriable=True))
        service, _ = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        import pytest

        with pytest.raises(ModelUpstreamError):
            await service.complete(
                _chat_request(app_code="demo"), identity=IDENTITY, trace_id="trace-004"
            )


class TestStreaming:
    async def _collect(self, service: object, request: ChatRequest, trace_id: str) -> list[object]:
        events = []
        async for envelope in service.stream_events(  # type: ignore[attr-defined]
            request, identity=IDENTITY, trace_id=trace_id
        ):
            events.append(envelope)
        return events

    async def test_event_sequence_node_chunks_done(self) -> None:
        gateway = ScriptedGateway(chunks=("你", "好", "世界"))
        service, factory = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        events = await self._collect(
            service, _chat_request(app_code="demo", stream=True), "trace-010"
        )
        kinds = [e.event for e in events]
        assert kinds == ["node_started", "message_chunk", "message_chunk", "message_chunk", "done"]
        seqs = [e.data["seq"] for e in events[1:4]]
        assert seqs == [0, 1, 2]
        done_event = events[-1]
        assert done_event.data["usage"] == {
            "promptTokens": 120,
            "completionTokens": 30,
            "totalTokens": 150,
            "credits": 7,
        }
        assert done_event.data["finishReason"] == "stop"
        # 信封必填字段
        for envelope in events:
            assert envelope.trace_id == "trace-010"
            assert envelope.conversation_id
        # 落库：assistant 消息为拼接全文
        repo = SqlAlchemyConversationRepository(factory)
        conversation_id = events[0].conversation_id
        messages = repo.recent_messages(TENANT, conversation_id, limit=10)
        assert messages[-1].content == "你好世界"

    async def test_upstream_error_yields_error_event(self) -> None:
        gateway = ScriptedGateway(error=ModelUpstreamError("上游挂了", retriable=True))
        service, _ = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        events = await self._collect(
            service, _chat_request(app_code="demo", stream=True), "trace-011"
        )
        assert [e.event for e in events] == ["node_started", "error"]
        assert events[-1].data["code"] == "MODEL_UPSTREAM_ERROR"
        assert events[-1].data["retriable"] is True

    async def test_quota_error_yields_error_event(self) -> None:
        gateway = ScriptedGateway()
        quota = InMemoryQuotaGuard(default_daily_tokens=5)
        service, _ = make_chat_service(
            gateway=gateway, profiles={"demo": DEMO_APP_CONFIG}, quota=quota
        )
        events = await self._collect(
            service, _chat_request(app_code="demo", stream=True), "trace-012"
        )
        assert [e.event for e in events] == ["node_started", "error"]
        assert events[-1].data["code"] == "QUOTA_EXCEEDED"

    async def test_midstream_interrupt_still_persists_partial(self) -> None:
        gateway = ScriptedGateway(chunks=("部", "分"), error_at_chunk=1)
        service, factory = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        events = await self._collect(
            service, _chat_request(app_code="demo", stream=True), "trace-013"
        )
        assert events[-1].event == "error"
        repo = SqlAlchemyConversationRepository(factory)
        conversation_id = events[0].conversation_id
        messages = repo.recent_messages(TENANT, conversation_id, limit=10)
        assert messages[-1].content == "部"  # 中断也留痕（可回放）


class TestConversationOwnership:
    async def test_foreign_conversation_rejected(self) -> None:
        gateway = ScriptedGateway()
        service, _factory = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        # 先以本租户建会话
        outcome = await service.complete(
            _chat_request(app_code="demo"), identity=IDENTITY, trace_id="trace-020"
        )
        foreign = TenantIdentity(tenant_id="t-other", user_id="u-9", key_id="k-9")
        import pytest

        from linkai_runtime.domain.errors import ConversationNotFoundError

        with pytest.raises(ConversationNotFoundError):
            await service.complete(
                _chat_request(app_code="demo", conversation_id=outcome.conversation_id),
                identity=foreign,
                trace_id="trace-021",
            )

    async def test_history_loaded_for_app_mode(self) -> None:
        gateway = ScriptedGateway()
        service, _factory = make_chat_service(gateway=gateway, profiles={"demo": DEMO_APP_CONFIG})
        first = await service.complete(
            _chat_request(app_code="demo"), identity=IDENTITY, trace_id="trace-030"
        )
        await service.complete(
            _chat_request(app_code="demo", conversation_id=first.conversation_id),
            identity=IDENTITY,
            trace_id="trace-031",
        )
        # 第二次调用：装配进历史（第一轮问答）
        _kind, request, _ctx = gateway.calls[-1]
        contents = [m.content for m in request.messages]
        assert "今天天气怎么样？" in contents  # 第一轮的问题进了历史
        assert contents[-1] == "今天天气怎么样？"  # 本轮问题在末尾
