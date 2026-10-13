"""领域异常——不依赖任何框架（铁律 2）。"""

from __future__ import annotations


class DomainError(Exception):
    """模型框架领域异常基类。

    携带 `code` 供 api 层翻译成契约里的错误体（`schemas/common.yaml#/Error`），
    携带 `retriable` 供降级链判断是否切备选模型。
    """

    code: str = "MODEL_DOMAIN_ERROR"
    retriable: bool = False

    def __init__(self, message: str, *, retriable: bool | None = None) -> None:
        super().__init__(message)
        if retriable is not None:
            self.retriable = retriable


class ModelNotFoundError(DomainError):
    """请求的模型编码在目录/租户绑定中不存在。"""

    code = "MODEL_NOT_FOUND"


class AdapterNotRegisteredError(DomainError):
    """模型所属厂商没有注册适配器——属于部署配置缺失，应在健康检查暴露。"""

    code = "ADAPTER_NOT_REGISTERED"


class CredentialMissingError(DomainError):
    """租户未配置该厂商的可用凭证（平台 Key 或用户自带 Key 均无）。"""

    code = "CREDENTIAL_MISSING"


class ProviderCallError(DomainError):
    """厂商返回错误或网络异常。

    默认 `retriable=True`：厂商 5xx/超时/限流都属于可降级场景，
    由 `FallbackPlanner` 决定是否切备选。4xx 语义错误应显式传 `retriable=False`。
    """

    code = "PROVIDER_CALL_FAILED"
    retriable = True


class ProviderRateLimitedError(ProviderCallError):
    """厂商 429——可降级，且建议退避后重试同模型。"""

    code = "PROVIDER_RATE_LIMITED"


class ProviderUnavailableError(ProviderCallError):
    """厂商不可用（5xx / 连接失败 / 超时）。"""

    code = "PROVIDER_UNAVAILABLE"


class ModelCallFailure(DomainError):
    """降级链全部候选都失败——终局错误，已无备选可切。"""

    code = "MODEL_CALL_FAILED"
