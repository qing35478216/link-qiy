"""领域异常——不依赖任何框架（铁律 2：domain 是纯 Python）。

三个正交维度（与 model-proxy 的 errors.py 保持同一约定）：
- `code`：稳定的机器码，进错误体的 `code` 字段（排障/客户端分支）；
- `retriable`：调用方是否值得原样重试（SSE error 事件携带给消费端）；
- `client_status`：映射到 HTTP 的状态码（api 层用；流式模式下不走 HTTP，
  改由 `error` 事件透传 code/message/retriable）。
"""

from __future__ import annotations


class DomainError(Exception):
    """runtime 领域异常基类。"""

    code: str = "RUNTIME_ERROR"
    retriable: bool = False
    client_status: int = 400

    def __init__(
        self,
        message: str,
        *,
        retriable: bool | None = None,
        client_status: int | None = None,
    ) -> None:
        super().__init__(message)
        if retriable is not None:
            self.retriable = retriable
        if client_status is not None:
            self.client_status = client_status


class UnauthorizedError(DomainError):
    """API Key 缺失/无效/已吊销（用户面鉴权失败）。"""

    code = "UNAUTHORIZED"
    client_status = 401


class InvalidRequestError(DomainError):
    """请求语义非法（如应用模式下缺少用户消息）。"""

    code = "INVALID_REQUEST"
    client_status = 400


class AppConfigUnavailableError(DomainError):
    """应用设定读取失败（platform 不可达/服务间鉴权未配）。

    上游问题，对客户端可重试；现象即 Phase 0 技术债信号——
    platform 的服务间端点就绪后本错误应消失。
    """

    code = "APP_CONFIG_UNAVAILABLE"
    retriable = True
    client_status = 502


class ContextOverflowError(DomainError):
    """装配后的 prompt 超出上下文预算（系统提示词/问题本身超长）。

    属于应用配置错误（contextLength 配太小或提示词过长），客户端修正配置后可重试。
    """

    code = "CONTEXT_OVERFLOW"
    client_status = 400


class QuotaExceededError(DomainError):
    """配额/积分不足（契约 service-api.yaml：POST /chat/completions 429）。"""

    code = "QUOTA_EXCEEDED"
    client_status = 429


class ConversationNotFoundError(DomainError):
    """conversationId 指定的会话不存在或不属于该租户（铁律 6）。"""

    code = "CONVERSATION_NOT_FOUND"
    client_status = 404


class ModelUpstreamError(DomainError):
    """model-proxy 调用失败（上游 5xx/网络/协议错误）。

    retriable 由上游 error 事件的 retriable 字段透传；对客户端是 502。
    """

    code = "MODEL_UPSTREAM_ERROR"
    retriable = True
    client_status = 502
