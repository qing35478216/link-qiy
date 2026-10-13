# services/billing — 变现框架（T-007）

积分钱包 / 统一计量原子扣减 / 充值订单 / 四档权益矩阵 / 对账校准。
**资金域零容错**：金额一律整数积分/分，禁浮点；所有写路径幂等；
资金 PR 双人评审（AGENTS.md 人类检查点 4）。

## 本地开发

    cd services/billing && uv sync --all-extras
    uv run uvicorn linkai_billing.main:app --reload   # 端口 8010

Schema 由 Alembic 管理（启动不自动建表）：

    DATABASE_URL=sqlite+pysqlite:////tmp/billing.db uv run alembic upgrade head

测试（领域层覆盖率 ≥70% 为门禁；沙箱需 --basetemp）：

    .venv/bin/python -m pytest --basetemp=/tmp/xxx

## 端点（Phase 0）

控制台面（Bearer JWT，与 platform 共享密钥）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/wallet` | 积分余额 + 版本 + 提醒状态 |
| POST | `/v1/wallet/check-in` | 每日签到（幂等：同日一次，57 积分） |
| PUT | `/v1/wallet/reminder-threshold` | 余额提醒阈值 |
| GET | `/v1/recharge/packages` | 四档套餐（1000/¥2.9 ~ 500000/¥800） |
| POST | `/v1/recharge/orders` | 创建充值订单（幂等：requestId） |
| POST | `/v1/recharge/orders/{orderNo}/pay` | Mock 支付（验签入账） |
| GET | `/v1/recharge/orders` | 订单列表 |
| GET | `/v1/usage/records` | 全维度流水（cursor 分页） |
| GET | `/quota/summary` | 契约 QuotaSummary（真实余额/用量） |
| POST | `/v1/quota/check` | 权益用量校验（超限 403 QUOTA_EXCEEDED） |

内部面（X-Internal-Token）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/internal/v1/metering/events` | 消费 MeteringEvent（幂等键 = eventId） |
| GET | `/internal/v1/quota/summary` | platform 拉真实配额（替换占位 0） |
| PUT | `/internal/v1/tenants/{tenantId}/plan` | 版本同步（platform 事件） |
| POST | `/internal/v1/recharge/callback` | 支付回调（HMAC 验签 + 重放窗口 + 幂等） |
| POST | `/internal/v1/reconciliation/run` | 对账（Redis 流水 vs DB 明细） |

## 关键设计（详见 ADOPTED-TOOLS.md 与源码 docstring）

- **原子扣减选型 = DB 行锁路线**：条件 UPDATE（`balance + delta >= 0`）+
  唯一约束（`tenant_id, request_id`）幂等。不采用 Redis Lua——单一事实源、
  数据库级幂等不变量、CI 可真实并发验证（详见 infra/wallet_repo.py 模块 docstring）。
- **事件流水 = Redis Streams**：XADD 入流 → XREADGROUP+XAUTOCLAIM 消费 →
  XACK；至少一次投递 + 幂等消费 = 恰好一次效果。对账 XRANGE 全量比对。
- **入账规则**：FAILED 不计费（delta=0 留痕）；余额不足 BLOCKED 留痕
  （终态化，不追溯补扣）；免费模型 0 积分 applied。
- **对账告警**：差异率 > 0.01% → alert + frozen_settlement 信号（工程规范）。

## 文档

领域规则随 PR 更新（文档即代码，AGENTS.md 铁律 7）：价格口径
docs/01 第十部分；统一计量 docs/03 §3.4②；契约 packages/contracts。
