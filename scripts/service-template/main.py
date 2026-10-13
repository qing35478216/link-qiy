"""LinkAI __SERVICE_NAME__ 服务入口（四层架构：api -> services -> domain <- infra）。

约定：
- 健康检查 GET /healthz（api/health.py），compose / K8s probe 统一指向它
- OTel FastAPI 自动插桩：所有请求自动带 trace_id（docs/observability.md）
"""
from __future__ import annotations

from fastapi import FastAPI

from linkai___MODULE__.api.health import router as health_router

app = FastAPI(title="linkai-__SERVICE_NAME__", version="0.1.0")
app.include_router(health_router)

# OTel 插桩（服务脚手架后由 bootstrap 统一启用，保持与 observability.md 一致）：
#
#   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
#   FastAPIInstrumentor.instrument_app(app)
