"""应用装配——依赖注入与生命周期。

四层架构的"接线板"：这里才知道具体的infra 实现（内存目录、内存计量、
厂商出网客户端），api 层因此保持只做协议转换。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from linkai_model_proxy.domain.fallback import FallbackPlanner, RetryPolicy
from linkai_model_proxy.domain.metering import CreditCalculator
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.domain.routing import ModelInvocationService
from linkai_model_proxy.infra.adapters import ExternalAdapterFactory, register_builtins
from linkai_model_proxy.infra.catalog_seed import DEFAULT_MODEL_CATALOG
from linkai_model_proxy.infra.http_client import VendorHttpClient
from linkai_model_proxy.infra.memory import (
    HeuristicTokenEstimator,
    InMemoryCredentialStore,
    InMemoryModelCatalog,
    InMemoryTelemetrySink,
)
from linkai_model_proxy.infra.ssrf import SsrfPolicy
from linkai_model_proxy.services.gateway import ModelGatewayService
from linkai_model_proxy.services.playground import PlaygroundService

#: 出网白名单：默认覆盖 5 家内置厂商的 API 域名。
#: 租户自定义模型需把 base_url 主机加进配置（或部署时设 LINKAI_SSRF_ALLOWED_HOSTS）。
#:
#: 注意：厂商域名会随其云平台调整（如通义国际版/ 智谱新域名），因此这里同时
#: 保留若干"同平台泛域名"条目兜底。`*` 只匹配子域、不匹配裸域（见 ssrf.py），
#: 故裸域需单独列出。T-005 交付时本表实际用到的是前 5 条。
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    # —— 5 家内置厂商（当前实际使用）——
    "api.openai.com",
    "api.anthropic.com",
    "api.deepseek.com",
    "dashscope.aliyuncs.com",  # 通义千问（国内）
    "open.bigmodel.cn",  # 智谱 GLM
    # —— 泛域名兜底（厂商换域名时不至于立刻断线；引入前需人工核对）——
    "dashscope-intl.aliyuncs.com",  # 通义千问（国际）
    "*.bigmodel.cn",
    "api.moonshot.cn",  # Kimi（Phase 1 若接入需先确认 OpenAI 兼容性）
    "api.lkeap.cloud.baidu.com",  # 文心（Phase 1）
    "api.siliconflow.cn",  # 硅基流动（聚合类，Phase 1 评估）
)


def _env_hosts() -> frozenset[str]:
    raw = os.environ.get("LINKAI_SSRF_ALLOWED_HOSTS", "")
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return frozenset(hosts)


def build_ssrf_policy() -> SsrfPolicy:
    """从环境变量构造 SSRF 策略。"""
    hosts = _env_hosts() or frozenset(DEFAULT_ALLOWED_HOSTS)
    return SsrfPolicy(
        allowed_hosts=hosts,
        # 开发态可通过环境变量放开 http；生产必须保持 False
        allow_http=os.environ.get("LINKAI_SSRF_ALLOW_HTTP", "false").lower() == "true",
        connect_timeout_s=float(os.environ.get("LINKAI_HTTP_CONNECT_TIMEOUT", "5")),
        read_timeout_s=float(os.environ.get("LINKAI_HTTP_READ_TIMEOUT", "60")),
    )


def build_credential_store() -> InMemoryCredentialStore:
    """平台公共 Key——从环境变量注入（生产应换 KMS/DB 加密列）。"""
    providers = ("openai", "anthropic", "deepseek", "qwen", "glm")
    keys = {p: os.environ.get(f"LINKAI_PROVIDER_KEY_{p.upper()}", "") for p in providers}
    return InMemoryCredentialStore(
        platform_keys={p: k for p, k in keys.items() if k},
    )


@dataclass(slots=True)
class AppContainer:
    """应用级依赖容器。"""

    http: VendorHttpClient
    registry: AdapterRegistry
    catalog: InMemoryModelCatalog
    telemetry: InMemoryTelemetrySink
    credentials: InMemoryCredentialStore
    invoker: ModelInvocationService
    gateway: ModelGatewayService
    playground: PlaygroundService

    async def aclose(self) -> None:
        await self.http.aclose()


def build_container(
    *,
    extra_adapters: Sequence[tuple[str, ExternalAdapterFactory]] = (),
    max_attempts: int = 2,
) -> AppContainer:
    """组装完整依赖图。

    `extra_adapters` 是**厂商扩展的注入点**——外部包无需改动本服务代码
    即可接入新厂商（铁律 4 的运行期形态）。
    """
    http = VendorHttpClient(build_ssrf_policy())
    registry = register_builtins(AdapterRegistry(), http, extra=extra_adapters)
    catalog = InMemoryModelCatalog(public_models=DEFAULT_MODEL_CATALOG)
    telemetry = InMemoryTelemetrySink()
    credentials = build_credential_store()

    invoker = ModelInvocationService(
        registry=registry,
        catalog=catalog,
        credentials=credentials,
        telemetry=telemetry,
        estimator=HeuristicTokenEstimator(),
        planner=FallbackPlanner(
            policy=RetryPolicy(
                max_attempts=max_attempts,
                backoff_base_ms=int(os.environ.get("LINKAI_RETRY_BACKOFF_MS", "200")),
            )
        ),
        credit_calculator=CreditCalculator(),
    )
    gateway = ModelGatewayService(invoker)
    return AppContainer(
        http=http,
        registry=registry,
        catalog=catalog,
        telemetry=telemetry,
        credentials=credentials,
        invoker=invoker,
        gateway=gateway,
        playground=PlaygroundService(gateway),
    )


@lru_cache(maxsize=1)
def get_container() -> AppContainer:
    """FastAPI 依赖注入用的单例（应用生命周期内）。"""
    return build_container()
