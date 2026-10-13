"""模型框架领域层：实体、值对象、端口接口、纯领域服务。

铁律 2（架构）：本包**不得** import 任何框架（fastapi/httpx/sqlalchemy/pydantic 等），
只依赖Python 标准库与 `typing`。可单测，不碰 DB、不发网络请求。
架构守卫测试见 `tests/unit/test_architecture_guard.py`（AST 扫描强制）。
"""

from linkai_model_proxy.domain.adapter import (
    AdapterCapabilities,
    AdapterRegistration,
    ModelAdapter,
    ProviderAdapter,
    ProviderCredential,
)
from linkai_model_proxy.domain.errors import (
    AdapterNotRegisteredError,
    CredentialMissingError,
    DomainError,
    ModelNotFoundError,
    ProviderCallError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from linkai_model_proxy.domain.fallback import FallbackDecision, FallbackPlanner, RetryPolicy
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
from linkai_model_proxy.domain.metering import (
    CreditCalculator,
    MeteringEvent,
    MeteringOutcome,
)
from linkai_model_proxy.domain.model_card import (
    ModelCapability,
    ModelCard,
    ModelCatalogSnapshot,
    ModelPrice,
    ModelRef,
    ProviderId,
)
from linkai_model_proxy.domain.ports import (
    CredentialResolver,
    ModelCatalog,
    TelemetrySink,
    TokenEstimator,
)
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.domain.routing import InvocationContext, ModelInvocationService

__all__ = [
    "AdapterCapabilities",
    "AdapterNotRegisteredError",
    "AdapterRegistration",
    "AdapterRegistry",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "Choice",
    "CredentialMissingError",
    "CredentialResolver",
    "CreditCalculator",
    "DomainError",
    "FallbackDecision",
    "FallbackPlanner",
    "FinishReason",
    "InvocationContext",
    "MessageRole",
    "MeteringEvent",
    "MeteringOutcome",
    "ModelAdapter",
    "ModelCallFailure",
    "ModelCapability",
    "ModelCard",
    "ModelCatalog",
    "ModelCatalogSnapshot",
    "ModelInvocationService",
    "ModelNotFoundError",
    "ModelPrice",
    "ModelRef",
    "ProviderAdapter",
    "ProviderCallError",
    "ProviderCredential",
    "ProviderId",
    "ProviderRateLimitedError",
    "ProviderUnavailableError",
    "RetryPolicy",
    "StreamDelta",
    "TelemetrySink",
    "TokenEstimator",
    "TokenUsage",
]
