"""对外 OpenAI 兼容接口——契约 `service-api.yaml` 的实现。

端点：
- `POST /v1/chat/completions` ——对话补全（`stream=true` 时按 runtime-events 出SSE）
- `GET  /v1/models`          ——可调用模型列表

SSE 事件协议依据 `runtime-events.yaml`：`message_chunk` 逐片、`done` 携usage
与 finishReason 收尾、`error` 为异常终局。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from linkai_model_proxy.api.auth import CallerIdentity, resolve_caller
from linkai_model_proxy.api.dependencies import AppContainer, get_container
from linkai_model_proxy.api.schemas import (
    ChatCompletionRequestIn,
    ChatCompletionResponseOut,
    ChatMessageOut,
    ChoiceOut,
    ModelListOut,
    ModelOut,
    PriceOut,
    UsageOut,
)
from linkai_model_proxy.domain.errors import DomainError
from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatRequest,
    MessageRole,
)
from linkai_model_proxy.domain.model_card import ModelCard
from linkai_model_proxy.domain.routing import InvocationContext

router = APIRouter(prefix="/v1", tags=["Chat", "Models"])


def _to_domain_request(payload: ChatCompletionRequestIn) -> ChatRequest:
    """契约 DTO → 领域对象（只做协议转换，不含业务）。"""
    return ChatRequest(
        model=payload.model_,
        messages=tuple(
            ChatMessage(
                role=MessageRole(m.role),
                content=m.content,
                name=m.name,
                tool_call_id=m.tool_call_id,
            )
            for m in payload.messages
        ),
        stream=payload.stream,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        app_code=payload.app_code,
        conversation_id=payload.conversation_id,
        variables=payload.variables,
    )


def _to_model_out(card: ModelCard) -> ModelOut:
    return ModelOut(
        code=card.code,
        name=card.name,
        provider=card.provider,
        capabilities=[str(c) for c in card.capabilities],
        context_length=card.context_length,
        price=PriceOut(
            input_per_1k=card.price.input_per_1k,
            output_per_1k=card.price.output_per_1k,
            credit_per_call=card.price.credit_per_call,
        ),
        enabled=card.enabled,
    )


@router.post(
    "/chat/completions",
    response_model=None,
    summary="对话补全（stream=true 时返回 SSE 事件流）",
    operation_id="createChatCompletion",
)
async def create_chat_completion(
    payload: ChatCompletionRequestIn,
    caller: Annotated[CallerIdentity, Depends(resolve_caller)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> Any:
    """对话补全。

    计量由网关内部强制完成——本层无法也无需关心。
    """
    request = _to_domain_request(payload)
    ctx = caller.to_context(app_code=payload.app_code, conversation_id=payload.conversation_id)

    if not request.stream:
        response = await container.gateway.chat(request, ctx)
        return ChatCompletionResponseOut(
            id=response.id,
            created=response.created,
            model=response.model,
            usage=UsageOut(
                promptTokens=response.usage.prompt_tokens,
                completionTokens=response.usage.completion_tokens,
                totalTokens=response.usage.total_tokens,
                credits=response.usage.credits,
            ),
            choices=[
                ChoiceOut(
                    index=choice.index,
                    message=ChatMessageOut(
                        role=str(choice.message.role),
                        content=choice.message.content,
                        name=choice.message.name,
                        tool_call_id=choice.message.tool_call_id,
                    ),
                    finish_reason=str(choice.finish_reason),
                )
                for choice in response.choices
            ],
        )

    return StreamingResponse(
        _sse_stream(container, request, ctx, request.conversation_id or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲，保证真流式
        },
    )


@router.get(
    "/models",
    response_model=ModelListOut,
    summary="可调用模型列表（元数据：编码/能力/价格/上下文长度）",
    operation_id="listModels",
)
async def list_models(
    caller: Annotated[CallerIdentity, Depends(resolve_caller)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> ModelListOut:
    """返回该租户可调用的模型。"""
    cards = container.gateway.list_models(caller.tenant_id)
    return ModelListOut(data=[_to_model_out(card) for card in cards])


async def _sse_stream(
    container: AppContainer,
    request: ChatRequest,
    ctx: InvocationContext,
    conversation_id: str,
) -> AsyncIterator[str]:
    """把领域流式增量转成 runtime-events 协议的 SSE 帧。

    事件序列（runtime-events.yaml v0.1.1）：
      `message_chunk*`（带 seq）→ `done`（带 usage + finishReason）
      异常终局：`error`（带 code/message/retriable）
    """
    trace_id = ctx.trace_id
    conv_id = conversation_id or request.conversation_id or trace_id

    try:
        async for delta in container.gateway.chat_stream(request, ctx):
            yield _sse_frame(
                _envelope(
                    "message_chunk",
                    {"delta": delta.delta, "seq": delta.seq},
                    trace_id=trace_id,
                    conversation_id=conv_id,
                )
            )
            if delta.is_terminal:
                usage = delta.usage
                yield _sse_frame(
                    _envelope(
                        "done",
                        {
                            "usage": {
                                "promptTokens": usage.prompt_tokens if usage else 0,
                                "completionTokens": usage.completion_tokens if usage else 0,
                                "totalTokens": usage.total_tokens if usage else 0,
                                "credits": usage.credits if usage else 0,
                            },
                            "finishReason": str(delta.finish_reason or "stop"),
                        },
                        trace_id=trace_id,
                        conversation_id=conv_id,
                    )
                )
    except DomainError as exc:
        # 领域异常 → error 事件（协议约定的异常终局，携带 retriable 供上层重试）
        yield _sse_frame(
            _envelope(
                "error",
                {"code": exc.code, "message": str(exc), "retriable": exc.retriable},
                trace_id=trace_id,
                conversation_id=conv_id,
            )
        )


def _envelope(
    event: str, data: dict[str, Any], *, trace_id: str, conversation_id: str
) -> dict[str, Any]:
    """构造 runtime-events 的事件信封。"""
    return {
        "event": event,
        "traceId": trace_id,
        "conversationId": conversation_id,
        "nodeId": None,
        "ts": _iso_now(),
        "data": data,
    }


def _sse_frame(payload: dict[str, Any]) -> str:
    """序列化一帧 SSE。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
