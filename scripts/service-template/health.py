"""统一健康检查端点：GET /healthz。

约定（scripts/service-template/README.md 硬约定 4）：
- 返回 {"status": "ok"} + HTTP 200，只表示进程存活
- 不做重依赖检查（DB/Redis 连通性另开 /readyz），避免探针风暴打挂依赖
- compose healthcheck、K8s liveness/readiness probe 一律指向 /healthz
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
