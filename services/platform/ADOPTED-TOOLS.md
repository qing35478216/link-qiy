# services/platform 开源选型记录（铁律 8）

> 通用模块动手前先检索 GitHub 成熟库；核查四项：① 近 3 个月有提交/发版 ② Issue 响应 ③ 许可证兼容（MIT/Apache-2.0/BSD 可直接引入）④ 技术栈与依赖版本匹配。
> 本文件记录 T-002 账户域引入的第三方库选型对比与理由。新依赖必须先进本文件再进 pyproject。

## 1. JWT 签发/校验：PyJWT（已引入，MIT）

| 候选 | 维护活跃度 | Issue 响应 | 许可证 | 适配度 | 结论 |
|---|---|---|---|---|---|
| **PyJWT**（jpadilla/pyjwt） | 活跃，2.15.x 系列持续发版（2026-09 仍有 release） | Issue 周转快，社区最大 | MIT | 纯 JWS 签发/校验，API 极简，无传递依赖（HMAC 模式） | **采用** |
| python-jose（mpdavis/python-jose） | 历史长期停滞，多起 CVE（2024 年 FastAPI 官方文档已迁走） | 差 | MIT | 功能全（JWE/JWK）但我们不需要 | 排除（安全记录差） |
| authlib（lepture/authlib） | 活跃 | 好 | BSD | 完整 OAuth/OIDC 套件，体量大（~10x PyJWT），我们是自建登录服务 | 排除（过重） |

**集成方式**：`infra/jwt_service.py` 的 `PyJwtTokenService` 实现 domain 定义的 `TokenService` 协议。
**必要适配**：① 显式 `algorithms=["HS256"]` 白名单防 alg=none；② 自定义 claims `sub/tid/typ/jti`（tid 承载多租户）；③ 生产密钥由 `LINKAI_JWT_SECRET` 注入（默认值仅本地开发，启动打警告）；④ 支持 `leeway` 参数便于测试过期用例。
**自研理由**：不适用（JWS 标准实现无需自研；HMAC 签名手写等于自造密码学风险）。

## 2. ORM / 迁移：SQLAlchemy 2.0 + Alembic（已引入，均为 MIT）

- 技术栈基线即 FastAPI + SQLAlchemy + PostgreSQL（工单指定），无备选对比必要；Alembic 是 SQLAlchemy 生态事实标准。
- 使用约束：ORM 模型只出现在 infra 层；所有仓储方法签名强制带 tenant_id；迁移只加通用类型（String/DateTime），保证 PG16 与测试 SQLite 双跑。

## 3. 结构化日志：structlog（已引入，MIT / Apache-2.0 双许可）

- docs/observability.md 明确约定"Python：structlog + 从 OTel context 取 trace_id"，属约定选型非自由发挥。
- 适配：`_add_trace_ids` processor 从 OTel span context 注入 trace_id/span_id；service 名经 contextvars 绑定，每条日志必带。

## 4. 未引入项（Phase 0 用内存实现，接口已按 Redis 形态预留）

| 需求 | Phase 0 实现 | 计划替换 |
|---|---|---|
| 扫码票据/短信验证码存储 | `InMemorySmsCodeStore` / `MockWechatProvider`（进程内） | Redis（key 前缀 + TTL，`SmsCodeStore` 协议不变） |
| 事件总线 | `InMemoryMessageBus`（服务内同步） | MQ（UserCreated → billing 开户，Outbox 保证可靠投递） |
| 真实微信/短信 | Mock Provider（`WechatProvider`/`SmsProvider` 协议 + 注册机制） | 微信开放平台 / 短信厂商适配器 |

理由：Phase 0 出口链路跑通优先；三处均按 domain 协议编程，替换不改业务代码（铁律 4 注册机制）。

## 依赖清单（对应 pyproject，版本由 uv.lock pin）

| 库 | 版本约束 | 许可证 | 引入理由 |
|---|---|---|---|
| pyjwt | >=2.9 | MIT | JWT 签发/校验（见 §1） |
| sqlalchemy | >=2.0 | MIT | ORM（仅 infra 层） |
| alembic | >=1.13 | MIT | 数据库迁移骨架 |
| psycopg[binary] | >=3.2 | LGPL-3.0 | PostgreSQL 官方驱动（compose 默认栈） |
| structlog | >=24.1 | MIT/Apache-2.0 | 结构化日志（observability.md 约定） |
| fastapi / uvicorn[standard] / opentelemetry-* | 脚手架基线 | — | 模板自带 |
| httpx / pytest / pytest-cov / ruff / mypy / black | dev | — | 测试与门禁 |

> psycopg 为 LGPL-3.0：以独立驱动形式链接使用（非修改库源码），SaaS 场景无传染要求；这是 PostgreSQL 生态唯一官方维护的 Python 3 驱动，无活跃替代（asyncpg 功能重复且迁移成本更高，Phase 1 视性能需求再评）。
