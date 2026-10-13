"""健康检查端点：GET /healthz（scripts/service-template 硬约定 4）。

只表示进程存活，不做重依赖检查（DB/model-proxy 连通性另开 /readyz），
避免探针风暴打挂依赖。compose healthcheck / K8s probe 一律指向它。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
