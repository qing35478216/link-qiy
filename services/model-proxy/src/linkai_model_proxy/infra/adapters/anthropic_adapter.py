"""Anthropic（Claude）适配器——**非** OpenAI 兼容，必须做协议翻译。

差异点（对照 OpenAI Chat Completions）：
| 维度 | OpenAI | Anthropic Messages |
|---|---|---|
| 端点 | `/chat/completions` | `/messages` |
| 鉴权头 | `Authorization: Bearer` | `x-api-key` + `anthropic-version` |
| system 消息 | 混在 messages 里 | **顶层独立字段** `system` |
| max_tokens | 可选 | **必填** |
| 响应内容 | `choices[].message.content` | `content[]` 内容块数组 |
| 用量 | `usage.prompt/completion_tokens` | `usage.input_tokens/output_tokens` |
| 结束原因 | `finish_reason` | `stop_reason`（值域不同：end_turn/max_tokens/tool_use） |

**不引入 `anthropic-sdk-python`**：虽然它是 MIT 且活跃，但 Anthropic Messages
是稳定的公开 HTTP API，我们只需要 4 个字段的映射；引入 SDK 会带来
httpx/pydantic/anyio 的重复依赖树（见 ADOPTED-TOOLS.md §2）。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from linkai_model_proxy.domain.adapter import (
    AdapterCapabilities,
    ProviderCredential,
)
from linkai_model_proxy.domain.errors import ProviderCallError
from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Choice,
    FinishReason,
    MessageRole,
    StreamDelta,
    TokenUsage,
)
from linkai_model_proxy.domain.model_card import ModelCard
from linkai_model_proxy.infra.http_client import JsonDict, ProviderCall, VendorHttpClient

#: Anthropic 强制要求 max_tokens，缺失会导致 400
DEFAULT_MAX_TOKENS = 1024

#: Anthropic 的默认 API 版本（跟随官方文档的稳定版本号）
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter:
    """Anthropic Messages API 适配器。"""

    PROVIDER: ClassVar[str] = "anthropic"
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.anthropic.com/v1"
    CHAT_PATH: ClassVar[str] = "/messages"
    CAPABILITIES: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_stream=True, supports_tools=True, supports_vision=True, reports_usage=True
    )
    ALLOW_BYOK: ClassVar[bool] = True

    def __init__(self, http: VendorHttpClient) -> None:
        self._http = http

    @property
    def provider(self) -> str:
        return self.PROVIDER

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self.CAPABILITIES

    async def complete(
        self,
        request: ChatRequest,
        *,
        card: ModelCard,
        credential: ProviderCredential,
    ) -> ChatResponse:
        body = await self._http.post_json(
            ProviderCall(
                url=self._endpoint(credential),
                payload=self.build_payload(request, card),
                headers=self.build_headers(credential),
            )
        )
        return self.parse_response(body, card)

    async def stream(
        self,
        request: ChatRequest,
        *,
        card: ModelCard,
        credential: ProviderCredential,
    ) -> AsyncIterator[StreamDelta]:
        payload = self.build_payload(request, card)
        payload["stream"] = True
        frames = await self._http.stream_sse(
            ProviderCall(
                url=self._endpoint(credential),
                payload=payload,
                headers=self.build_headers(credential),
            )
        )
        seq = 0
        text_parts: list[str] = []
        async for frame in frames:
            delta = self._parse_stream_frame(frame, seq)
            if delta is None:
                continue
            text_parts.append(delta.delta)
            seq += 1
            yield delta
        _ = text_parts  # 文本汇总由上层消费端负责

    # ---------- 协议翻译 ----------

    def build_payload(self, request: ChatRequest, card: ModelCard) -> JsonDict:
        """领域请求 → Anthropic Messages 请求。"""
        system_chunks = [m.content for m in request.messages if m.role is MessageRole.SYSTEM]
        conversation = [m for m in request.messages if m.role is not MessageRole.SYSTEM]

        payload: JsonDict = {
            "model": card.code,
            # Anthropic 不接受 role=tool 的裸消息，统一降级为 user（Phase 1 补工具协议）
            "messages": [
                {"role": self._map_role(m.role), "content": m.content} for m in conversation
            ],
            "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
        }
        if system_chunks:
            payload["system"] = "\n\n".join(system_chunks)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def build_headers(self, credential: ProviderCredential) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": credential.secret,
            "anthropic-version": ANTHROPIC_VERSION,
            **credential.extra_headers,
        }

    def parse_response(self, body: JsonDict, card: ModelCard) -> ChatResponse:
        """Anthropic 响应 → 领域响应。"""
        blocks = body.get("content")
        if not isinstance(blocks, list) or not blocks:
            raise ProviderCallError(
                f"Anthropic 响应缺少 content 块：{str(body)[:200]}", retriable=False
            )
        text = "".join(
            block["text"]
            for block in blocks
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        )
        return ChatResponse(
            id=str(body.get("id") or card.code),
            created=int(time.time()),
            model=str(body.get("model") or card.code),
            choices=(
                Choice(
                    index=0,
                    message=ChatMessage(role=MessageRole.ASSISTANT, content=text),
                    finish_reason=self._map_stop_reason(body.get("stop_reason")),
                ),
            ),
            usage=self._parse_usage(body.get("usage")),
        )

    def _parse_stream_frame(self, frame: JsonDict, seq: int) -> StreamDelta | None:
        """解析 Anthropic 流式事件。

        事件形态差异较大：`content_block_delta` 带增量文本，
        `message_delta` 带最终 stop_reason 与 usage，`message_stop` 为流终局。
        """
        event_type = frame.get("type")

        if event_type == "content_block_delta":
            delta_raw = frame.get("delta")
            if isinstance(delta_raw, dict) and isinstance(delta_raw.get("text"), str):
                return StreamDelta(delta=delta_raw["text"], seq=seq)
            return None

        if event_type == "message_delta":
            delta_raw = frame.get("delta")
            finish = FinishReason.STOP
            if isinstance(delta_raw, dict):
                finish = self._map_stop_reason(delta_raw.get("stop_reason"))
            return StreamDelta(
                delta="", seq=seq, finish_reason=finish, usage=self._parse_usage(frame.get("usage"))
            )

        # ping / content_block_start / message_start 等事件对上层无增量价值
        return None

    @staticmethod
    def _parse_usage(raw: Any) -> TokenUsage:
        if not isinstance(raw, dict):
            return TokenUsage.of(0, 0)
        prompt = raw.get("input_tokens")
        completion = raw.get("output_tokens")
        prompt_i = prompt if isinstance(prompt, int) and not isinstance(prompt, bool) else 0
        completion_i = (
            completion if isinstance(completion, int) and not isinstance(completion, bool) else 0
        )
        return TokenUsage.of(prompt_i, completion_i)

    @staticmethod
    def _map_role(role: MessageRole) -> str:
        """Anthropic 只接受 user / assistant。"""
        if role is MessageRole.ASSISTANT:
            return "assistant"
        return "user"

    @staticmethod
    def _map_stop_reason(raw: Any) -> FinishReason:
        """Anthropic stop_reason → 契约 finishReason。"""
        if isinstance(raw, str):
            if raw == "max_tokens":
                return FinishReason.LENGTH
            if raw == "tool_use":
                return FinishReason.TOOL_CALLS
        return FinishReason.STOP

    def _endpoint(self, credential: ProviderCredential) -> str:
        base = (credential.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        if not base:
            raise ProviderCallError(f"厂商 {self.PROVIDER!r} 未配置 base_url", retriable=False)
        return f"{base}{self.CHAT_PATH}"
