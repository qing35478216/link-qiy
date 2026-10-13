"""信任边界用例——锁死"不可伪造的数据不得流入计费"这条不变量。

背景（T-008 对齐时发现）：
Go 网关早期注入的是 `X-Subject-Id`，而 model-proxy 读的是 `X-User-Id`——
**两边名字不一致**，导致客户端伪造的 `X-User-Id` 畅通无阻，而真实身份反而读不到。
当时 `user_id` 尚未流入计量，因此未造成实际串账；这是数据流上的定时炸弹。

本文件的作用不是"测功能"，而是**让炸弹拆掉后无法被悄悄装回去**：
若将来有人把 `user_id` 接入 `InvocationContext` / `MeteringEvent`，
下面的用例会失败并提示先解决可信来源问题。
"""

from __future__ import annotations

import dataclasses

import pytest

from linkai_model_proxy.api.auth import (
    GATEWAY_SIGNATURE_HEADER,
    TENANT_HEADER,
    TRACE_HEADER,
    USER_HEADER,
    CallerIdentity,
    resolve_caller,
)
from linkai_model_proxy.domain.errors import TenantContextError
from linkai_model_proxy.domain.metering import MeteringEvent, MeteringOutcome
from linkai_model_proxy.domain.routing import InvocationContext


class TestHeaderNameContract:
    """头名必须与 T-008 网关实际注入的一致。"""

    def test_header_names_are_stable(self) -> None:
        """头名回归锁——改名字会让两端静默失联。"""
        assert TENANT_HEADER == "X-Tenant-Id"
        assert TRACE_HEADER == "X-Trace-Id"
        # T-008 曾注入 X-Subject-Id，已统一为 X-User-Id；此断言防止回退
        assert USER_HEADER == "X-User-Id"

    def test_signature_header_defined(self) -> None:
        assert GATEWAY_SIGNATURE_HEADER == "X-Gateway-Signature"


class TestTenantRequired:
    async def test_missing_tenant_rejected(self) -> None:
        with pytest.raises(TenantContextError):
            await resolve_caller(tenant_id=None)

    async def test_blank_tenant_rejected(self) -> None:
        with pytest.raises(TenantContextError):
            await resolve_caller(tenant_id="   ")

    async def test_oversized_tenant_rejected(self) -> None:
        with pytest.raises(TenantContextError):
            await resolve_caller(tenant_id="t" * 200)

    async def test_tenant_is_trimmed(self) -> None:
        identity = await resolve_caller(tenant_id="  tenant-a  ")
        assert identity.tenant_id == "tenant-a"


class TestUserIdNeverReachesBilling:
    """核心不变量：user_id 不得流入计量相关结构。"""

    def test_invocation_context_has_no_user_id_field(self) -> None:
        fields = {f.name for f in dataclasses.fields(InvocationContext)}
        assert "user_id" not in fields, (
            "InvocationContext 出现 user_id——该字段来自请求头，"
            "接入计量前必须先解决可信来源（否则可跨租户串账）"
        )

    def test_metering_event_has_no_user_id_field(self) -> None:
        fields = {f.name for f in dataclasses.fields(MeteringEvent)}
        assert "user_id" not in fields, "MeteringEvent 出现 user_id——计量归属必须只依赖 tenant_id"

    def test_metering_payload_keys_have_no_user(self) -> None:
        from datetime import UTC, datetime

        event = MeteringEvent(
            event_id="e",
            tenant_id="t",
            app_code=None,
            conversation_id=None,
            trace_id="tr",
            provider="openai",
            model_code="gpt-4o",
            outcome=MeteringOutcome.SUCCESS,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            credits=1,
            latency_ms=1,
            attempt=1,
            occurred_at=datetime.now(UTC),
        )
        assert "user_id" not in event.to_payload()
        assert "user" not in event.to_payload()

    async def test_to_context_drops_user_id(self) -> None:
        """即使 CallerIdentity 带 user_id，转成InvocationContext 时也必须丢弃。"""
        identity = CallerIdentity(tenant_id="t", trace_id="tr", user_id="victim-9999")
        ctx = identity.to_context()
        assert not hasattr(ctx, "user_id")
        assert "user_id" not in {f.name for f in dataclasses.fields(ctx)}

    async def test_resolve_caller_accepts_user_id_but_it_is_inert(self) -> None:
        """user_id 可被解析（供审计日志用），但不得影响任何决策。"""
        identity = await resolve_caller(tenant_id="t", trace_id="tr", user_id="someone")
        assert identity.user_id == "someone"
        ctx = identity.to_context()
        # 决策相关字段只应受 tenant_id 影响
        assert ctx.tenant_id == "t"


class TestMultiTenantIsolation:
    """铁律 6：租户上下文不可被伪造/混用。"""

    def test_context_requires_tenant(self) -> None:
        with pytest.raises(ValueError, match="tenant_id"):
            InvocationContext(tenant_id="", trace_id="tr")

    def test_context_carries_both_ids(self) -> None:
        ctx = InvocationContext(tenant_id="t1", trace_id="tr1", app_code="app")
        assert ctx.tenant_id == "t1"
        assert ctx.trace_id == "tr1"
        assert ctx.app_code == "app"

    def test_two_tenants_produce_distinct_contexts(self) -> None:
        a = InvocationContext(tenant_id="tenant-a", trace_id="t")
        b = InvocationContext(tenant_id="tenant-b", trace_id="t")
        assert a.tenant_id != b.tenant_id
