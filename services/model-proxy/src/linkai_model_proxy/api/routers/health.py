"""健康检查与注册中心自省。

`/healthz` 给 K8s 探针；`/healthz/providers` 暴露"注册了哪些厂商、各自能力"——
这是铁律 4 的**可观测证据**：新增厂商后无需看代码就能确认已生效。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from linkai_model_proxy.api.auth import CallerIdentity, resolve_caller
from linkai_model_proxy.api.dependencies import AppContainer, get_container
from linkai_model_proxy.infra.adapters import is_openai_compatible

router = APIRouter(tags=["Health"])


@router.get("/healthz", summary="存活/就绪探针")
async def healthz() -> dict[str, str]:
    """K8s 探针端点。不需要鉴权（不含业务数据）。"""
    return {"status": "ok"}


@router.get("/healthz/providers", summary="厂商适配器注册中心自省")
async def list_providers(
    caller: Annotated[CallerIdentity, Depends(resolve_caller)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    """列出已注册厂商及其能力声明。

    鉴权要求租户上下文——避免未授权方探测平台接了哪些厂商。
    """
    _ = caller
    providers = []
    for name, registration in sorted(container.registry.snapshot().items()):
        providers.append(
            {
                "provider": name,
                "protocol": "openai-compatible" if is_openai_compatible(name) else "native",
                "allowByok": registration.allow_byok,
                "capabilities": {
                    "supportsStream": registration.capabilities.supports_stream,
                    "supportsTools": registration.capabilities.supports_tools,
                    "supportsVision": registration.capabilities.supports_vision,
                    "reportsUsage": registration.capabilities.reports_usage,
                },
            }
        )
    return {"data": providers, "total": len(providers)}
