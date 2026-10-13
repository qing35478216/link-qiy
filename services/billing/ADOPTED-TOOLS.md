# services/billing 开源选型记录（铁律 8）

> 通用模块动手前先检索 GitHub 成熟库；核查四项：① 近 3 个月有提交/发版 ② Issue 响应 ③ 许可证兼容（MIT/Apache-2.0/BSD 可直接引入）④ 技术栈与依赖版本匹配。
> 本文件记录 T-007 变现框架引入的第三方库选型对比与理由。新依赖必须先进本文件再进 pyproject。
> 与 platform 重叠的基线依赖（FastAPI/SQLAlchemy/Alembic/psycopg/structlog/PyJWT）不重复论证，见 services/platform/ADOPTED-TOOLS.md。

## 1. Redis 客户端：redis-py（已引入，MIT）

| 候选 | 维护活跃度 | Issue 响应 | 许可证 | 适配度 | 结论 |
|---|---|---|---|---|---|
| **redis-py**（redis/redis-py） | Redis 官方维护，7.1.0 于 2025-11 发版（近 3 个月持续发版） | Issue 周转快，生态最大客户端 | MIT | Streams 全命令（XADD/XREADGROUP/XAUTOCLAIM/XACK/XRANGE/XPENDING）齐备，支持 Python 3.12 | **采用** |
| aioredis | 已并入 redis-py 异步层（官方明确 deprecated 独立包） | — | MIT | 重复 | 排除（并入主线） |
| valkey-py | Valkey 分支客户端，API 兼容 | 活跃 | BSD | 与 compose 栈（Redis7）不一致 | 排除（部署栈是 Redis） |

**集成方式**：`infra/redis_stream.py` 的 `RedisMeteringStream` 实现 domain 定义的 `MeteringEventStream` 端口（XADD/XREADGROUP/XAUTOCLAIM/XACK/XRANGE/XPENDING）；连接经 `REDIS_URL` 注入，为空时回落内存实现（dev/单进程）。
**必要适配**：① 消费组 `billing` 启动时 `XGROUP CREATE mkstream` 幂等建组（BUSYGROUP 忽略）；② streams 返回结构是运行时形态，显式 `Any` + `_collect` 统一解码收窄；③ 至少一次语义 = XREADGROUP `>`（新消息）+ XAUTOCLAIM min-idle 0（未决重投）。

## 2. 测试替身：fakeredis（已引入 dev，BSD-3-Clause）

| 候选 | 维护活跃度 | Issue 响应 | 许可证 | 适配度 | 结论 |
|---|---|---|---|---|---|
| **fakeredis**（MA3STR0/fakeredis-py，moransoftware 维护） | 2.28.x 系列活跃发版（2025-04 仍有 release） | open/closed 比健康 | BSD-3-Clause | 纯 Python，25/25 Stream 命令（含 XAUTOCLAIM/XREADGROUP/XPENDING），与 redis-py 同 API | **采用** |
| 自研内存 fake | — | — | — | Streams + 消费组 + 未决语义自研成本高、易与真实 Redis 行为漂移 | 排除（有成熟库） |
| 测试依赖真实 Redis | — | — | — | CI 需起服务，沙箱/并行 agent 不友好 | 排除（Phase 0 门禁要无依赖可跑） |

**集成方式**：`tests/services/test_metering_ingest.py` 用 `FakeStrictRedis()` 驱动 `RedisMeteringStream`，证明 Redis 路径语义（append/read_group/ack/redeliver）无需真实服务器；`pytest.importorskip` 兜底。
**自研理由**：不适用。

## 3. 原子扣减实现：DB 行锁路线（自研，工单要求二选一并记录理由）

工单允许"Redis Lua 或 DB 行锁二选一，记录选型理由"——选 **DB 行锁路线（条件 UPDATE + 唯一约束幂等）**，不引入 Lua 脚本与 Redis 双写：

1. **单一事实源**：余额与流水都在 PostgreSQL；Redis Lua 路线是"Redis 原子扣 + 异步落库"，存在双写一致窗口，对账与客诉都难解释；
2. **幂等由唯一约束硬保证**：`(tenant_id, request_id)` 唯一索引让"同一 request_id 只生效一次"成为数据库级不变量，不依赖 Lua 脚本正确性与 Redis 持久化配置（AOF everysec 最多丢 1 秒，资金域不可接受）；
3. **单语句原子**：`UPDATE wallets SET balance = balance + :delta WHERE tenant_id = :t AND balance + :delta >= 0` 在行锁下串行执行，rowcount=0 即余额不足——无竞态、无重试、**绝不为负**；
4. **可测性**：SQLite（测试）与 PG（生产）渲染相同 SQL 形态，并发用例可在 CI 无 Redis 环境真实跑（10 线程 Barrier 统一发令 + 文件库独立连接）；fakeredis 对 EVAL 支持不完整，Redis Lua 路线无法在单测中证明脚本语义。

Redis 的定位收敛为：计量事件**流水**（Streams，见 §1）与对账数据源；热点余额读缓存预热留待 Phase 1+（QPS 驱动），且只读不承担扣减权威。

## 4. 支付渠道：Mock Provider（自研，工单指定）

Phase 0 无真实支付渠道，工单要求"Mock 支付 Provider"。自研理由：签名原语（HMAC-SHA256 + 规范化拼串 + compare_digest + 重放窗口）是与渠道无关的安全契约，真实渠道适配器（微信/支付宝）Phase 1 按铁律 4 注册机制接入；`domain/ports.PaymentProvider` 协议已冻结形状。

## 5. 依赖清单（对应 pyproject，版本由 uv.lock pin）

| 库 | 版本约束 | 许可证 | 引入理由 |
|---|---|---|---|
| redis | >=5.0 | MIT | Redis Streams 客户端（§1） |
| pyjwt | >=2.9 | MIT | JWT 校验（与 platform 共享密钥） |
| sqlalchemy | >=2.0 | MIT | ORM（仅 infra 层） |
| alembic | >=1.13 | MIT | 迁移 |
| psycopg[binary] | >=3.2 | LGPL-3.0 | PG 驱动（platform 同款论证） |
| structlog | >=24.1 | MIT/Apache-2.0 | 结构化日志（observability.md 约定） |
| fastapi / uvicorn / opentelemetry-* | 脚手架基线 | — | 模板自带 |
| fakeredis | >=2.28 | BSD-3-Clause | Redis 测试替身（§2，dev） |
| httpx / pytest / pytest-cov / pytest-asyncio / ruff / mypy | dev | — | 测试与门禁 |
