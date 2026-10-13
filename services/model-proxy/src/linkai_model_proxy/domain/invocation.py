"""统一调用模型——网关内外共用的规范形态（OpenAI 兼容语义，但用平台自己的类型）。

契约依据：`packages/contracts/openapi/service-api.yaml#/components/schemas/ChatCompletionRequest`
与 `.../ChatCompletionResponse`。本层是纯领域对象，不含 pydantic/框架依赖；
api 层负责在领域对象与契约 DTO 之间互转。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MessageRole(StrEnum):
    """消息角色。取值与契约 `ChatMessage.role` 枚举严格一致。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(StrEnum):
    """结束原因。取值与契约 `choices[].finishReason` 枚举严格一致。"""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """单条对话消息。"""

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """转 OpenAI 兼容 dict（省略 None 字段，减少厂商侧解析差异）。"""
        payload: dict[str, object] = {"role": str(self.role), "content": self.content}
        if self.name is not None:
            payload["name"] = self.name
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        return payload


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """token 用量。字段名对齐契约 `ChatCompletionResponse.usage`。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    credits: int = 0

    @classmethod
    def of(cls, prompt_tokens: int, completion_tokens: int) -> TokenUsage:
        """便捷构造：total 自动求和，credits 交由计量层回填。"""
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """一次对话补全请求（领域规范形态）。

    `stream=True` 时 `ModelInvocationService` 返回流式结果，调用方逐块消费
    `StreamDelta`；`stream=False` 时返回一次性 `ChatResponse`。
    """

    model: str
    messages: tuple[ChatMessage, ...]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    app_code: str | None = None
    conversation_id: str | None = None
    variables: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("model 不能为空")
        if not self.messages:
            raise ValueError("messages 不能为空")


@dataclass(frozen=True, slots=True)
class Choice:
    """单个候选结果。"""

    index: int
    message: ChatMessage
    finish_reason: FinishReason = FinishReason.STOP


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """一次非流式对话补全结果。"""

    id: str
    created: int
    model: str
    choices: tuple[Choice, ...]
    usage: TokenUsage = field(default_factory=lambda: TokenUsage.of(0, 0))

    @property
    def content(self) -> str:
        """便捷取首条消息文本——Playground 与降级链回放常用。"""
        if not self.choices:
            return ""
        return self.choices[0].message.content


@dataclass(frozen=True, slots=True)
class StreamDelta:
    """流式增量。

    `usage` 仅在终局分片携带（厂商在最后一帧返回用量），中间分片为None。
    """

    delta: str
    seq: int
    finish_reason: FinishReason | None = None
    usage: TokenUsage | None = None

    @property
    def is_terminal(self) -> bool:
        return self.finish_reason is not None
