"""LinkAI runtime 服务入口（四层架构：api -> services -> domain <- infra）。

约定：
- 健康检查 GET /healthz（api/health.py），compose / K8s probe 统一指向它
- OTel FastAPI 自动插桩：所有请求自动带 trace_id（docs/observability.md）
- Schema 由 Alembic 管理（alembic/versions/）；本服务启动不自动建表
- 依赖装配见 api/app.py 的 lifespan → api/deps.build_container

本地开发：

    cd services/runtime && uv sync
    alembic upgrade head
    uv run uvicorn linkai_runtime.main:app --reload --port 8010
"""

from __future__ import annotations

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from linkai_runtime.api.app import create_app
from linkai_runtime.infra.logging import setup_logging

app = create_app()
FastAPIInstrumentor.instrument_app(app)
setup_logging("linkai-runtime", "info")
