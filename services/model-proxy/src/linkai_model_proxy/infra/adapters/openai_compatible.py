"""OpenAI 兼容适配器基类——多数厂商的共用实现。

为什么走 OpenAI 兼容 HTTP 而非各家专有 SDK（铁律 8 选型结论）：
① **许可证**：各家 Python SDK 许可混杂（见 ADOPTED-TOOLS.md §2），专有 SDK 会把
   GPL/AGPL/非商用条款引入 SaaS 服务，存在传染与商用合规风险；
② **依赖体积**：引入 5 家的 SDK 会带来数十个传递依赖，供应链面显著扩大；
③ **维护成本**：专有 SDK 各自升级、API 形态各异；OpenAI 兼容接口是最小公倍数，
   差异只在 `base_url` 与少量字段映射，适配器 = 十几行配置；
④ **可测试**：统一的请求/响应形态让回放用例可以共用同一套断言。

Anthropic 不兼容 OpenAI 格式，因此单独实现（见 `anthropic_adapter.py`）。
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


class OpenAICompatibleAdapter:
    """OpenAI 兼容协议适配器。

    子类只需覆盖类属性（`PROVIDER` / `DEFAULT_BASE_URL` / `CHAT_PATH`），
    绝大多数厂商**不需要**写任何方法。特殊差异才覆写钩子方法。
    """

    #: 厂商标识（与 `ModelCard.provider` 一致）
    PROVIDER: ClassVar[str] = ""
    #: 官方 OpenAI 兼容端点
    DEFAULT_BASE_URL: ClassVar[str] = ""
    #: 补全路径
    CHAT_PATH: ClassVar[str] = "/chat/completions"
    #: 能力声明
    CAPABILITIES: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_stream=True, supports_tools=False, reports_usage=True
    )
    #: 是否允许用户自带 Key（BYOK）
    ALLOW_BYOK: ClassVar[bool] = True
    #: 是否显式传stream 参数（部分 OpenAI 兼容厂商对 stream 支持有差异）
    SUPPORTS_STREAM: ClassVar[bool] = True

    def __init__(self, http: VendorHttpClient) -> None:
        self._http = http

    # ---------- ModelAdapter 协议实现 ----------

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
        payload = self.build_payload(request, card)
        body = await self._http.post_json(
            ProviderCall(
                url=self._endpoint(credential, self.CHAT_PATH),
                payload=payload,
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
        if self.SUPPORTS_STREAM:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}

        started = time.monotonic()
        frames = await self._http.stream_sse(
            ProviderCall(
                url=self._endpoint(credential, self.CHAT_PATH),
                payload=payload,
                headers=self.build_headers(credential),
            )
        )
        seq = 0
        async for frame in frames:
            delta = self._parse_stream_frame(frame, seq)
            if delta is None:
                continue
            seq += 1
            yield delta
        _ = time.monotonic() - started  # 延迟由上层计量记录

    # ---------- 可覆写钩子 ----------

    def build_payload(self, request: ChatRequest, card: ModelCard) -> JsonDict:
        """构造请求体——OpenAI 兼容字段直接映射。"""
        payload: JsonDict = {
            "model": self.map_model_code(card.code, request.model),
            "messages": [m.to_dict() for m in request.messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        self.extra_payload(payload, request, card)
        return payload

    def extra_payload(self, payload: JsonDict, request: ChatRequest, card: ModelCard) -> None:
        """厂商特有请求字段钩子。默认无。"""

    def map_model_code(self, card_code: str, requested_code: str) -> str:
        """模型编码映射钩子。

        默认透传平台模型编码；厂商需要不同命名时覆写
        （例如把平台统一编码映射到厂商的 `qwen-plus` / `glm-4-flash`）。
        """
        return card_code or requested_code

    def build_headers(self, credential: ProviderCredential) -> dict[str, str]:
        """鉴权头。默认 Bearer。"""
        headers = {"Content-Type": "application/json", **credential.extra_headers}
        headers["Authorization"] = f"Bearer {credential.secret}"
        return headers

    def parse_response(self, body: JsonDict, card: ModelCard) -> ChatResponse:
        """解析非流式响应。字段差异的厂商覆写此方法。"""
        choices_raw = body.get("choices")
        if not isinstance(choices_raw, list) or not choices_raw:
            raise ProviderCallError(f"厂商响应缺少 choices：{str(body)[:200]}", retriable=False)
        choices: list[Choice] = []
        for index, raw in enumerate(choices_raw):
            if not isinstance(raw, dict):
                continue
            message_raw = raw.get("message")
            if not isinstance(message_raw, dict):
                continue
            content = message_raw.get("content")
            if not isinstance(content, str):
                content = ""
            choices.append(
                Choice(
                    index=int(raw.get("index", index)),
                    message=ChatMessage(role=MessageRole.ASSISTANT, content=content),
                    finish_reason=_parse_finish_reason(raw.get("finish_reason")),
                )
            )
        if not choices:
            raise ProviderCallError("厂商响应 choices 结构不可解析", retriable=False)

        return ChatResponse(
            id=str(body.get("id") or card.code),
            created=int(body.get("created") or int(time.time())),
            model=str(body.get("model") or card.code),
            choices=tuple(choices),
            usage=_parse_usage(body.get("usage")),
        )

    def _parse_stream_frame(self, frame: JsonDict, seq: int) -> StreamDelta | None:
        """解析单帧 SSE。无可用增量时返回 None（该帧被跳过）。"""
        choices_raw = frame.get("choices")
        usage_raw = frame.get("usage")
        usage = _parse_usage(usage_raw) if isinstance(usage_raw, dict) else None

        if not isinstance(choices_raw, list) or not choices_raw:
            # 部分厂商在末帧单独回 usage、choices 为空——仍需产出终局分片
            if usage is not None:
                return StreamDelta(delta="", seq=seq, finish_reason=FinishReason.STOP, usage=usage)
            return None

        first = choices_raw[0]
        if not isinstance(first, dict):
            return None
        delta_raw = first.get("delta")
        text = ""
        if isinstance(delta_raw, dict):
            raw_content = delta_raw.get("content")
            if isinstance(raw_content, str):
                text = raw_content
        finish_raw = first.get("finish_reason")
        finish = _parse_finish_reason(finish_raw) if isinstance(finish_raw, str) else None

        if not text and finish is None and usage is None:
            return None
        return StreamDelta(delta=text, seq=seq, finish_reason=finish, usage=usage)

    def _endpoint(self, credential: ProviderCredential, path: str) -> str:
        base = (credential.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        if not base:
            raise ProviderCallError(f"厂商 {self.PROVIDER!r} 未配置 base_url", retriable=False)
        return f"{base}{path}"


def _parse_usage(raw: Any) -> TokenUsage:
    """解析 OpenAI 兼容 usage 结构；缺失或非法时返回全 0（上层会用估算器补齐）。"""
    if not isinstance(raw, dict):
        return TokenUsage.of(0, 0)
    prompt = _as_int(raw.get("prompt_tokens"))
    completion = _as_int(raw.get("completion_tokens"))
    total = _as_int(raw.get("total_tokens")) or (prompt + completion)
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def _parse_finish_reason(raw: Any) -> FinishReason:
    """厂商可能返回 `stop`/`length`/`tool_calls` 或中文/自定义值，统一收敛到契约枚举。"""
    if isinstance(raw, str):
        try:
            return FinishReason(raw)
        except ValueError:
            return FinishReason.STOP
    return FinishReason.STOP


def _as_int(raw: Any) -> int:
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    return 0
