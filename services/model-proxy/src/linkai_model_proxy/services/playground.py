"""Playground——控制台侧模型试玩。

三条硬约束：
1. **走网关**：Playground 内部调 `ModelGatewayService`，与其他调用路径完全一致，
   因此天然继承降级链与计量埋点（"不准绕过计量直接调模型"）；
2. **强制计量**：每次试玩都产生 MeteringEvent，Playground 消耗同样计入租户积分
   （否则就是个免费刷模型的漏洞）；
3. **不写死提示词**：Playground 只传用户输入，默认 system 提示词来自请求，
   平台不内置业务提示词（角色定义铁律）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkai_model_proxy.domain.invocation import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    MessageRole,
)
from linkai_model_proxy.domain.routing import InvocationContext
from linkai_model_proxy.services.gateway import ModelGatewayService

#: Playground 的默认温度——平台给一个可用起点，用户可改
DEFAULT_TEMPERATURE = 0.7

#: Playground 允许的最大输入长度（防误粘贴整篇文档打爆计费）
MAX_INPUT_CHARS = 32_000


@dataclass(frozen=True, slots=True)
class PlaygroundRequest:
    """一次试玩请求。"""

    model: str
    prompt: str
    system: str | None = None
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("model 不能为空")
        if not self.prompt.strip():
            raise ValueError("prompt 不能为空")
        if len(self.prompt) > MAX_INPUT_CHARS:
            raise ValueError(f"prompt 超长（上限 {MAX_INPUT_CHARS} 字符）")

    def to_chat_request(self) -> ChatRequest:
        """转成网关的领域请求。"""
        messages: list[ChatMessage] = []
        if self.system and self.system.strip():
            messages.append(ChatMessage(role=MessageRole.SYSTEM, content=self.system))
        messages.append(ChatMessage(role=MessageRole.USER, content=self.prompt))
        return ChatRequest(
            model=self.model,
            messages=tuple(messages),
            stream=False,  # Playground v1 用非流式，够用且便于展示 token
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


@dataclass(frozen=True, slots=True)
class PlaygroundResult:
    """一次试玩结果。"""

    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    credits: int
    finish_reason: str


class PlaygroundService:
    """Playground 用例服务。"""

    def __init__(self, gateway: ModelGatewayService) -> None:
        self._gateway = gateway

    async def play(self, request: PlaygroundRequest, ctx: InvocationContext) -> PlaygroundResult:
        """执行一次试玩。计量照常发生——由网关负责。"""
        response: ChatResponse = await self._gateway.chat(request.to_chat_request(), ctx)
        usage = response.usage
        finish = response.choices[0].finish_reason if response.choices else "stop"
        return PlaygroundResult(
            model=response.model,
            content=response.content,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            credits=usage.credits,
            finish_reason=str(finish),
        )

    def suggest_models(self, tenant_id: str) -> list[str]:
        """给控制台推荐可试玩模型（只给有对话能力的）。"""
        from linkai_model_proxy.domain.model_card import ModelCapability

        return [
            card.code
            for card in self._gateway.list_models(tenant_id)
            if card.supports(ModelCapability.CHAT)
        ]


@dataclass(frozen=True, slots=True)
class PlaygroundSession:
    """多轮试玩会话（Playground 保留上下文）。

    Phase 0 最小可用：进程内按 `(tenant_id, session_id)` 存历史。
    Phase 1 换 Redis —— 领域接口不变。
    """

    tenant_id: str
    session_id: str
    messages: list[ChatMessage] = field(default_factory=list)

    def append(self, message: ChatMessage) -> None:
        self.messages.append(message)

    def to_chat_request(self, model: str, **kwargs: object) -> ChatRequest:
        return ChatRequest(model=model, messages=tuple(self.messages), **kwargs)  # type: ignore[arg-type]
