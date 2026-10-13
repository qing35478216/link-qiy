"""网关用例服务——对外（api层与下游服务）唯一入口。

存在的意义：api 层不直接碰 `ModelInvocationService`，所有跨用例的横切逻辑
（默认参数收敛、模型可用性检查、trace 注入）集中在这里。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from linkai_model_proxy.domain.invocation import (
    ChatRequest,
    ChatResponse,
    StreamDelta,
)
from linkai_model_proxy.domain.model_card import ModelCard
from linkai_model_proxy.domain.routing import InvocationContext, ModelInvocationService


class ModelGatewayService:
    """统一模型网关用例服务。"""

    def __init__(self, invoker: ModelInvocationService) -> None:
        self._invoker = invoker

    async def chat(self, request: ChatRequest, ctx: InvocationContext) -> ChatResponse:
        """非流式对话补全（含降级链与计量）。"""
        return await self._invoker.complete(request, ctx)

    def chat_stream(
        self, request: ChatRequest, ctx: InvocationContext
    ) -> AsyncIterator[StreamDelta]:
        """流式对话补全（含降级链与计量）。"""
        return self._invoker.stream(request, ctx)

    def list_models(self, tenant_id: str) -> list[ModelCard]:
        """可调用模型列表（已过滤未注册适配器的厂商）。"""
        return self._invoker.list_models(tenant_id)

    def describe_model(self, tenant_id: str, code: str) -> ModelCard:
        """单个模型详情。"""
        return self._invoker.describe_model(tenant_id, code)
