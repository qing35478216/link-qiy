"""对话路由——契约 `service-api.yaml` POST /v1/chat/completions 的实现。

- stream=false（默认，v0.1.1 契约修复点）：返回完整 ChatCompletionResponse JSON
- stream=true：返回 text/event-stream，事件序列按 runtime-events.yaml v0.1.1：
  node_started → message_chunk*(seq 从 0) → done(usage+finishReason)；
  异常终局 error(code/message/retriable)。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from linkai_runtime.api.deps import AppContainer, CallerDep, ContainerDep, resolve_trace_id
from linkai_runtime.api.schemas import (
    ChatCompletionRequestIn,
    ChatCompletionResponseOut,
    ChatMessageOut,
    ChoiceOut,
    UsageOut,
)
from linkai_runtime.domain.chat import ChatMessage, ChatRequest, MessageRole
from linkai_runtime.domain.events import EventEnvelope
from linkai_runtime.domain.ports import TenantIdentity

router = APIRouter(prefix="/v1", tags=["Chat"])


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


@router.post(
    "/chat/completions",
    response_model=None,
    summary="对话补全（stream=false 返回 JSON；stream=true 返回 SSE 事件流）",
    operation_id="createChatCompletion",
)
async def create_chat_completion(
    payload: ChatCompletionRequestIn,
    request: Request,
    caller: CallerDep,
    container: ContainerDep,
) -> object:
    trace_id = resolve_trace_id(request)
    chat_request = _to_domain_request(payload)

    if not chat_request.stream:
        outcome = await container.chat_service.complete(
            chat_request, identity=caller, trace_id=trace_id
        )
        response = outcome.response
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
                        toolCallId=choice.message.tool_call_id,
                    ),
                    finishReason=str(choice.finish_reason),
                )
                for choice in response.choices
            ],
        )

    return StreamingResponse(
        _sse_stream(container, chat_request, caller, trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲，保证真流式
        },
    )


async def _sse_stream(
    container: AppContainer,
    chat_request: ChatRequest,
    caller: TenantIdentity,
    trace_id: str,
) -> AsyncIterator[str]:
    """把 Runtime Event 序列化为 SSE 帧（每帧一个 data: JSON）。"""
    async for envelope in container.chat_service.stream_events(
        chat_request, identity=caller, trace_id=trace_id
    ):
        yield _sse_frame(envelope)


def _sse_frame(envelope: EventEnvelope) -> str:
    return f"data: {json.dumps(envelope.to_dict(), ensure_ascii=False)}\n\n"
