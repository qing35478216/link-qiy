# LinkAI Python 服务脚手架模板

新服务 5 分钟脚手架化（Phase 0 约定，验收标准 3）：

```bash
# 在仓库根目录执行，服务名用 snake_case
./scripts/new-service.sh <service-name>          # Python 服务，生成到 services/<name>/
./scripts/new-service.sh <service-name> --go     # Go 服务（gateway / sandbox 类）
```

生成内容（Python）：

```
services/<name>/
├── pyproject.toml        # FastAPI + ruff + mypy strict + pytest 配置（uv 管理）
├── README.md
├── .env.example
└── src/linkai_<name>/
    ├── main.py           # FastAPI 入口
    ├── api/              # ① 接口层：Router / 参数校验 / 鉴权 / 序列化（只做协议转换）
    │   └── health.py     #    GET /healthz —— 全公司统一健康检查端点
    ├── services/         # ② 应用层：业务编排、事务边界、领域事件发布
    ├── domain/           # ③ 领域层：纯 Python，禁止 import 任何框架（铁律 2），可单测
    └── infra/            # ④ 基础设施层：SQLAlchemy / Redis / MQ / 外部客户端实现
```

## 硬约定（违反即打回）

1. **四层依赖只准向内**：api → services → domain；infra 实现 domain 定义的接口
2. **domain 层零框架依赖**：不准 import fastapi / sqlalchemy / pydantic，只准标准库 + 纯 Python
3. **所有查询带 tenant_id**（铁律 6），仓储接口签名必须含 tenant_id
4. **健康检查统一 `GET /healthz`**：返回 `{"status": "ok"}`，HTTP 200；compose healthcheck /
   K8s liveness/readiness probe 一律指向它；不许在 /healthz 里做重依赖检查（另开 /readyz）
5. **结构化日志 + OTel trace_id 贯通**：见 docs/observability.md
6. **Go 服务**（gateway/sandbox）：四层结构同构（handler/service/domain/internal），
   golangci-lint 进 gate；go.mod 单 module 暂按服务独立 module，后续视情况收敛

## 启用服务后必须做的事

- 在根 `Makefile` 的 `gate` 目标里把对应 TODO 注释替换为真实 lint/test 命令
- 在 `.github/workflows/gate.yml` 把对应占位步骤替换为真实步骤
- pyproject 中 `dependencies` 的任何新增 = 工单"依赖清单"（铁律：版本 pin + license）
