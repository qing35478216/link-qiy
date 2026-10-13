"""API 层契约 DTO——**严格对齐** `packages/contracts/openapi/service-api.yaml`。

铁律 1：契约只读。本文件是契约的手写镜像（不重新生成，避免与何约的
`openapi-python-client` 产物产生第二事实源）。若契约变更，
由 Contract Engineer 改 yaml → 重新生成 → 本文件同步，**我不单方面改契约**。

字段命名从契约的 camelCase 直译到 Python snake_case，转换只发生在这一层。
"""

from __future__ import annotations

from typing import Any, Literal

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
    """契约 `ChatCompletionRequest`。"""

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
    """契约 `ChatCompletionResponse.usage`。"""

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

    model_config = ConfigDict(populate_by_name=True)

    index: int
    message: ChatMessageOut
    finish_reason: str = Field(default="stop", alias="finishReason")


class ChatCompletionResponseOut(BaseModel):
    """契约 `ChatCompletionResponse`。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    created: int
    model: str
    usage: UsageOut
    choices: list[ChoiceOut]


# ---------- Model（契约 v0.1.1）----------


class PriceOut(BaseModel):
    """契约 `Model.price`。"""

    model_config = ConfigDict(populate_by_name=True)

    input_per_1k: float = Field(default=0.0, alias="inputPer1k")
    output_per_1k: float = Field(default=0.0, alias="outputPer1k")
    credit_per_call: int = Field(default=0, alias="creditPerCall")


class ModelOut(BaseModel):
    """契约 `Model`。"""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    name: str
    provider: str
    capabilities: list[str]
    context_length: int = Field(default=0, alias="contextLength")
    price: PriceOut
    enabled: bool = True


class ModelListOut(BaseModel):
    """契约 `GET /models` 响应（`{data: Model[]}`）。"""

    data: list[ModelOut]


# ---------- Playground（控制台内部接口，非契约面）----------

#: 说明：契约 `console-api.yaml` v0.1.1 **没有** Playground 端点。
#: 本工单不擅自改契约（铁律 1），Playground 先以服务内部路由提供，
#: 路径前缀 `/_internal/playground` 表明其非对外契约面。
#: 契约缺口已上报 T-015，待 Contract Engineer 在 v0.2 补 `POST /playground/completions`。


class PlaygroundRequestIn(BaseModel):
    """Playground 试玩请求。"""

    model_config = ConfigDict(populate_by_name=True)

    model_: str = Field(alias="model")
    prompt: str = Field(min_length=1)
    system: str | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, alias="maxTokens", ge=1, le=32_000)


class PlaygroundResponseOut(BaseModel):
    """Playground 试玩响应。"""

    model_config = ConfigDict(populate_by_name=True)

    model: str
    content: str
    usage: UsageOut
    finish_reason: str = Field(default="stop", alias="finishReason")


# ---------- 错误体（对齐 schemas/common.yaml#/Error）----------


class ErrorOut(BaseModel):
    """契约 `Error`。"""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    request_id: str = Field(alias="requestId")
    details: dict[str, Any] | None = None
