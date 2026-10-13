# services/platform — 平台后端

账户域 / 应用域（配置七件套）/ 配额域 / 团队域。Python + FastAPI + SQLAlchemy + PostgreSQL + Redis，四层架构 api→services→domain→infra。

领地：平台后端工程师（backend-platform）。

## 本地开发（T-002 账户域已落地）

```bash
cd services/platform
uv sync --extra dev
# 1. 建库（docker compose up -d 后有 PG；本地无 PG 可用 sqlite 冒烟）
export DATABASE_URL=postgresql+psycopg://linkai:linkai_dev_password@localhost:5432/linkai
uv run alembic upgrade head
# 2. 起服务
export LINKAI_JWT_SECRET=$(openssl rand -hex 32)   # 生产必须强随机
uv run uvicorn linkai_platform.main:app --reload
# 3. 冒烟
curl -s localhost:8000/healthz   # {"status":"ok"}
```

## 测试与门禁

```bash
uv run pytest                 # 领域层覆盖率 ≥70%（--cov-fail-under=70）
uv run ruff check . && uv run ruff format --check .
uv run black --check .
uv run mypy                   # --strict（pyproject 已配）
```

注意：本机 pytest 需显式 `--basetemp`（沙箱对共享临时目录并发 mkdir 有限制）：
`uv run pytest --basetemp=.tmp/bt`。

## 架构边界（铁律）

- domain 层纯 Python：禁止 import fastapi/sqlalchemy/pydantic；实体/值对象/仓储协议/领域规则
- infra 层实现 domain 协议；ORM 只出现在 infra（models.py / 各 repo 实现）
- 所有查询带 tenant_id（UserRepository 签名强制 + tests/infra/test_tenant_isolation.py 证明）
- 写操作发 MeteringEvent 的位置在应用域/配额域（T-003+）；账户域当前只发 UserCreated（MessageBus）
- 契约事实源：packages/contracts/openapi/console-api.yaml v0.1.1（Auth/Users 段）

## 目录

```
src/linkai_platform/
├── api/         # ① 路由 + Pydantic（health/auth/users/deps/errors/schemas）
├── services/    # ② 编排（auth_service/user_service）
├── domain/      # ③ 纯 Python（users/auth/rules/events/repositories）
└── infra/       # ④ SQLAlchemy/PyJWT/Mock Provider/内存总线/日志/配置
alembic/         # 迁移（0001_account 初始表）
tests/           # domain / infra / api 三层
ADOPTED-TOOLS.md  # 开源选型记录（铁律 8）
```

## Mock 驱动（Phase 0）

- 微信扫码：`MockWechatProvider`（票据状态机；`LINKAI_WECHAT_MOCK_AUTO_CONFIRM_SECONDS>0` 自动确认，仅联调用）
- 短信：`MockSmsProvider`（验证码进结构化日志；`InMemorySmsCodeStore.peek_code()` 仅供测试/联调读取）
