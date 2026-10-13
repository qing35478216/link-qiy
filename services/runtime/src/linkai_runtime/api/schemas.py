"""API 层契约 DTO——**严格对齐** `packages/contracts/openapi/service-api.yaml` v0.1.1。

铁律 1：契约只读。本文件是契约的手写镜像（不重新生成，避免产生第二事实源）。
若契约变更，由 Contract Engineer 改 yaml → 重新生成 → 本文件同步。

关键契约语义（v0.1.1 修复点）：
- `stream` **默认 false**：不传该字段返回完整 JSON；传 true 才走 SSE 事件流。
- 流式响应的事件协议见 runtime-events.yaml（done 为正常终局）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------- ChatCompletionRequest（契约 v0.1.1）----------


class ChatMessageIn(BaseModel):
    """契约 `ChatMessage`。"""

    model_config = ConfigDict(populate_by_name=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = Field(default=None, description="role=tool 时的插件名")
    tool_call_id: str | None = Field(default=None, alias="toolCallId")


class ChatCompletionRequestIn(BaseModel):
    """契约 `ChatCompletionRequest`（stream 默认 false 是 v0.1.1 明确修复点）。"""

    model_config = ConfigDict(populate_by_name=True)

    model_: str = Field(alias="model", description="模型编码（/v1/models 返回的 code）")
    messages: list[ChatMessageIn] = Field(min_length=1, description="至少一条消息")
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, alias="maxTokens")
    app_code: str | None = Field(default=None, alias="appCode")
    conversation_id: str | None = Field(default=None, alias="conversationId")
    variables: dict[str, str] = Field(default_factory=dict)


# ---------- ChatCompletionResponse（契约 v0.1.1）----------


class UsageOut(BaseModel):
    """契约 `ChatCompletionResponse.usage`（credits：本次对话消耗积分）。"""

    prompt_tokens: int = Field(alias="promptTokens")
    completion_tokens: int = Field(alias="completionTokens")
    total_tokens: int = Field(alias="totalTokens")
    credits: int = 0


class ChatMessageOut(BaseModel):
    """契约 `ChatCompletionResponse.choices[].message`。"""

    model_config = ConfigDict(populate_by_name=True)

    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")


class ChoiceOut(BaseModel):
    """契约 `choices[]`。"""

    index: int
    message: ChatMessageOut
    finish_reason: str = Field(default="stop", alias="finishReason")


class ChatCompletionResponseOut(BaseModel):
    """契约 `ChatCompletionResponse`（非流式完整响应）。"""

    id: str
    created: int
    model: str
    usage: UsageOut
    choices: list[ChoiceOut]


# ---------- Model（契约 GET /v1/models）----------


class PriceOut(BaseModel):
    """契约 `Model.price`。"""

    input_per_1k: float | None = Field(default=None, alias="inputPer1k")
    output_per_1k: float | None = Field(default=None, alias="outputPer1k")
    credit_per_call: int | None = Field(default=None, alias="creditPerCall")


class ModelOut(BaseModel):
    """契约 `Model`（透传 model-proxy 元数据）。"""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    name: str
    capabilities: list[str]
    provider: str | None = None
    context_length: int | None = Field(default=None, alias="contextLength")
    price: PriceOut | None = None
    enabled: bool | None = None


class ModelListOut(BaseModel):
    """契约 `GET /v1/models` 响应。"""

    data: list[ModelOut]
