"""领域异常——不依赖任何框架（铁律 2）。"""

from __future__ import annotations


class DomainError(Exception):
    """模型框架领域异常基类。

    三个正交维度，不要混用：
    - `code`：稳定的机器码，进错误体的 `code` 字段（排障/客户端分支）；
    - `retriable`：**降级链内部**判断——该错误是否值得切下一个候选模型；
    - `client_status`：映射到 HTTP 的状态码（api 层用）。

    注意 `retriable=False` 不等于"客户端错了"：`ModelCallFailure` 不可再降级
    （候选已耗尽），但它对客户端是 502（上游厂商问题）而非 400。
    """

    code: str = "MODEL_DOMAIN_ERROR"
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


class ModelNotFoundError(DomainError):
    """请求的模型编码在目录/租户绑定中不存在。"""

    code = "MODEL_NOT_FOUND"


class AdapterNotRegisteredError(DomainError):
    """模型所属厂商没有注册适配器——属于部署配置缺失，应在健康检查暴露。"""

    code = "ADAPTER_NOT_REGISTERED"
    # 部署问题：租户请求的模型本就不该被列出，客户端侧无从修正
    client_status = 500


class CredentialMissingError(DomainError):
    """租户未配置该厂商的可用凭证（平台 Key 或用户自带 Key 均无）。"""

    code = "CREDENTIAL_MISSING"
    # 租户可自行补 Key，因此是 4xx 而非 5xx
    client_status = 402


class ProviderCallError(DomainError):
    """厂商返回错误或网络异常。

    默认 `retriable=True`：厂商 5xx/超时/限流都属于可降级场景，
    由 `FallbackPlanner` 决定是否切备选。4xx 语义错误应显式传 `retriable=False`。
    """

    code = "PROVIDER_CALL_FAILED"
    retriable = True
    # 厂商侧问题——对客户端一律 502（"我这边上游坏了，可稍后重试"）
    client_status = 502


class ProviderRateLimitedError(ProviderCallError):
    """厂商 429——可降级，且建议退避后重试同模型。"""

    code = "PROVIDER_RATE_LIMITED"
    # 契约把 429 留给"配额/积分不足"（由 gateway/billing 判定），厂商限流走 502
    client_status = 502


class ProviderUnavailableError(ProviderCallError):
    """厂商不可用（5xx / 连接失败 / 超时）。"""

    code = "PROVIDER_UNAVAILABLE"
    client_status = 502


class ModelCallFailure(DomainError):
    """降级链全部候选都失败——终局错误，已无备选可切。

    `retriable=False`（不再降级）与 `client_status=502`（客户端可重试整个请求）
    并不矛盾：前者约束网关自身，后者描述对外语义。
    """

    code = "MODEL_CALL_FAILED"
    client_status = 502


class TenantContextError(DomainError):
    """缺少租户上下文——多租户隔离的硬性拒绝（铁律 6）。"""

    code = "TENANT_CONTEXT_REQUIRED"
    client_status = 400


class SsrfBlockedError(DomainError):
    """出网请求被 SSRF 闸门拦截。

    属于安全事件，对外不回显目标地址细节（避免探测），也不可重试。
    """

    code = "EGRESS_BLOCKED"
    client_status = 400
