"""model-proxy 客户端（实现 domain.ports.ModelGateway 协议）。

经 model-proxy 的 OpenAI 兼容端点调模型（团队规范：runtime 不准直连厂商 SDK，
厂商适配/降级/计量是 model-proxy 的职责）：
- 非流式：POST {base}/v1/chat/completions（stream=false）→ ChatCompletionResponse
- 流式：同端点（stream=true）→ 消费其 SSE 帧（message_chunk/done/error），
  转换为领域 StreamDelta 序列（runtime 再按 runtime-events 协议重发）

身份注入：X-Tenant-Id / X-Trace-Id（model-proxy 只信任网关注入的租户头，
见其 api/auth.py；生产由 Go gateway 强制注入并对外剥离）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping

import httpx

from linkai_runtime.domain.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Choice,
    FinishReason,
    MessageRole,
    StreamDelta,
    TokenUsage,
)
from linkai_runtime.domain.errors import ModelUpstreamError, QuotaExceededError
from linkai_runtime.domain.ports import InvocationContext

_CHAT_PATH = "/v1/chat/completions"
_MODELS_PATH = "/v1/models"


class HttpModelGateway:
    """HTTP 实现的模型网关客户端。"""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 120.0,
        connect_timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds)
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── 非流式 ────────────────────────────────────────────────

    async def complete(self, request: ChatRequest, ctx: InvocationContext) -> ChatResponse:
        headers = self._headers(ctx)
        payload = _to_proxy_payload(request, stream=False)
        try:
            response = await self._get_client().post(
                self._base_url + _CHAT_PATH, json=payload, headers=headers
            )
        except httpx.HTTPError as exc:
            raise ModelUpstreamError(f"model-proxy 调用失败：{exc}") from exc
        await _raise_for_proxy_status(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelUpstreamError("model-proxy 响应非 JSON") from exc
        return _to_chat_response(body)

    # ── 流式 ──────────────────────────────────────────────────

    async def stream(
        self, request: ChatRequest, ctx: InvocationContext
    ) -> AsyncIterator[StreamDelta]:
        headers = self._headers(ctx)
        payload = _to_proxy_payload(request, stream=True)
        client = self._get_client()
        try:
            async with client.stream(
                "POST", self._base_url + _CHAT_PATH, json=payload, headers=headers
            ) as response:
                await _raise_for_proxy_status(response)
                async for frame in _iter_sse_json(response):
                    event = frame.get("event")
                    data = frame.get("data")
                    if not isinstance(data, dict):
                        continue
                    if event == "message_chunk":
                        delta = data.get("delta")
                        seq = data.get("seq")
                        if isinstance(delta, str) and isinstance(seq, int):
                            yield StreamDelta(delta=delta, seq=seq)
                    elif event == "done":
                        usage = _parse_usage(data.get("usage"))
                        finish = data.get("finishReason")
                        yield StreamDelta(
                            delta="",
                            seq=-1,
                            finish_reason=_parse_finish_reason(finish),
                            usage=usage,
                        )
                    elif event == "error":
                        code = data.get("code")
                        message = data.get("message")
                        retriable = data.get("retriable")
                        raise ModelUpstreamError(
                            f"model-proxy 错误事件：{code} {message}",
                            retriable=bool(retriable) if isinstance(retriable, bool) else True,
                        )
        except httpx.HTTPError as exc:
            raise ModelUpstreamError(f"model-proxy 流式调用中断：{exc}") from exc

    # ── 模型列表 ──────────────────────────────────────────────

    async def list_models(self, tenant_id: str) -> list[Mapping[str, object]]:
        headers = {"X-Tenant-Id": tenant_id}
        try:
            response = await self._get_client().get(self._base_url + _MODELS_PATH, headers=headers)
        except httpx.HTTPError as exc:
            raise ModelUpstreamError(f"model-proxy 模型列表调用失败：{exc}") from exc
        await _raise_for_proxy_status(response)
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, Mapping)]

    # ── 内部 ──────────────────────────────────────────────────

    def _headers(self, ctx: InvocationContext) -> dict[str, str]:
        return {"X-Tenant-Id": ctx.tenant_id, "X-Trace-Id": ctx.trace_id}


async def _iter_sse_json(response: httpx.Response) -> AsyncIterator[Mapping[str, object]]:
    """解析 SSE 帧：每帧 `data: {json}`，产出解析后的字典。

    兼容 `data:[DONE]` 哨兵（跳过）；空行/注释行忽略。
    """
    data_lines: list[str] = []
    async for raw in response.aiter_lines():
        line = raw.strip()
        if not line:
            if data_lines:
                yield _parse_frame("\n".join(data_lines))
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    if data_lines:
        yield _parse_frame("\n".join(data_lines))


def _parse_frame(payload: str) -> Mapping[str, object]:
    if payload == "[DONE]":
        return {}
    try:
        frame = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ModelUpstreamError(f"model-proxy SSE 帧非法 JSON：{payload[:120]}") from exc
    return frame if isinstance(frame, dict) else {}


async def _raise_for_proxy_status(response: httpx.Response) -> None:
    """model-proxy 非 2xx → 领域异常。

    429 映射配额不足（契约：用户面 429 = 配额/积分不足）；5xx/网络映射 502。
    流式响应的 body 未消费时先 aread()，否则读错误详情会抛 ResponseNotRead。
    """
    if response.is_success:
        return
    if not response.is_closed:
        await response.aread()
    detail = _error_detail(response)
    if response.status_code == 429:
        raise QuotaExceededError(f"配额/积分不足：{detail}")
    raise ModelUpstreamError(
        f"model-proxy 返回 HTTP {response.status_code}：{detail}",
        retriable=response.status_code >= 500,
    )


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        code = body.get("code")
        message = body.get("message")
        if isinstance(message, str):
            return f"{code} {message}" if isinstance(code, str) else message
    return response.text[:200]


def _to_proxy_payload(request: ChatRequest, *, stream: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": request.model,
        "messages": [m.to_dict() for m in request.messages],
        "stream": stream,
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_tokens is not None:
        payload["maxTokens"] = request.max_tokens
    return payload


def _to_chat_response(body: object) -> ChatResponse:
    """model-proxy 的 ChatCompletionResponse JSON → 领域对象。"""
    if not isinstance(body, dict):
        raise ModelUpstreamError("model-proxy 响应形态非法")
    choices_raw = body.get("choices")
    choices: list[Choice] = []
    if isinstance(choices_raw, list):
        for index, item in enumerate(choices_raw):
            if not isinstance(item, dict):
                continue
            message_raw = item.get("message")
            if not isinstance(message_raw, dict):
                continue
            role = message_raw.get("role")
            content = message_raw.get("content")
            name_raw = message_raw.get("name")
            index_raw = item.get("index")
            finish = item.get("finishReason")
            if not isinstance(role, str) or not isinstance(content, str):
                continue
            choices.append(
                Choice(
                    index=index_raw
                    if isinstance(index_raw, int) and not isinstance(index_raw, bool)
                    else index,
                    message=ChatMessage(
                        role=MessageRole(role),
                        content=content,
                        name=name_raw if isinstance(name_raw, str) else None,
                    ),
                    finish_reason=_parse_finish_reason(finish),
                )
            )
    response_id = body.get("id")
    created_raw = body.get("created")
    model_raw = body.get("model")
    return ChatResponse(
        id=response_id if isinstance(response_id, str) else "",
        created=created_raw
        if isinstance(created_raw, int) and not isinstance(created_raw, bool)
        else 0,
        model=model_raw if isinstance(model_raw, str) else "",
        choices=tuple(choices),
        usage=_parse_usage(body.get("usage")),
    )


def _parse_usage(raw: object) -> TokenUsage:
    if not isinstance(raw, dict):
        return TokenUsage.of(0, 0)
    prompt = raw.get("promptTokens")
    completion = raw.get("completionTokens")
    total = raw.get("totalTokens")
    credits = raw.get("credits")
    prompt_n = prompt if isinstance(prompt, int) else 0
    completion_n = completion if isinstance(completion, int) else 0
    if not isinstance(total, int):
        total = prompt_n + completion_n
    credits_n = credits if isinstance(credits, int) else 0
    return TokenUsage(
        prompt_tokens=prompt_n,
        completion_tokens=completion_n,
        total_tokens=total,
        credits=credits_n,
    )


def _parse_finish_reason(raw: object) -> FinishReason:
    try:
        return FinishReason(str(raw))
    except ValueError:
        return FinishReason.STOP
