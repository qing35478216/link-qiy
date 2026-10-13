# task-runner —— 断点续传任务进程管理机制

> 防因断网 / 系统休眠 / 进程中断导致任务失败：本地 SQLite 进程表记录任务 ID、进度、状态与已完成数据；启动自动检测未完成任务并从中断点无缝恢复；关键节点实时落盘，异常退出不重复、不丢失；网络类失败自动退避重试 + 连通性探测。

## 为什么需要它

AI 团队实战教训（2026-10-13 夜）：五条并行 lane 分别死于 429 限流、网络不可达（ENETUNREACH）、空流、回合被取消——**进程状态只活在内存里，一死全丢**。本机制把"任务进程"变成可持久、可恢复、可重试的一等公民。

## 架构

```
┌────────────────────────────────────────────────────┐
│ TaskRunner.run(task_id, handler)                   │
│   loop:                                            │
│     RETRY_WAIT? ──到期──▶ NetworkProbe 探测          │
│        │网不通 → 顺延（覆盖休眠唤醒）                 │
│     start → RUNNING → handler(ctx)                  │
│        ├─ 成功 → complete(result) → SUCCEEDED       │
│        └─ 异常 → classify_error                     │
│             transient → RETRY_WAIT(退避) ──耗尽──▶ DEAD│
│             permanent → FAILED                     │
│             fatal     → 原样抛出                    │
├────────────────────────────────────────────────────┤
│ ResumeContext                                      │
│   .data / .completed_steps / .step(name, fn) 幂等   │
│   .save(data) ──每次 step 立即落库──▶                │
├────────────────────────────────────────────────────┤
│ TaskProcessManager（SQLite，WAL，单事务迁移）        │
│   tasks 表：id/kind/status/payload/checkpoint/      │
│   retry_count/max_retries/last_error/next_retry_at/ │
│   result/heartbeat_at                               │
└────────────────────────────────────────────────────┘
```

## 状态机

```
PENDING ─start─▶ RUNNING ─complete─▶ SUCCEEDED
  ▲                │  │
  │           recover_stale  fail(permanent)
  │                ▼      ▼
reset─ PAUSED      RETRY_WAIT ─次数耗尽─▶ DEAD
                   fail(transient)
```

- `RUNNING` 是易逝态：进程消失后永远停在 RUNNING，靠 `heartbeat_at` 超期判定中断
- `PAUSED`：启动恢复时由 `recover_stale()` 翻成，等待无缝续跑
- `DEAD`：重试耗尽，必须人工 `reset` 后重跑

## 四类保证（都有测试背书，24/24 通过）

1. **不丢失**：只有写进 checkpoint 的步骤才算完成；每个 `step()` 立即落库
2. **不重复**：`completed_steps` 是幂等依据；跨进程重建上下文后，已完成步骤直接返回缓存值
3. **恢复无缝**：启动 `recover_stale()` → PAUSED → `handler` 从 `ctx.data` 继续
4. **失败自愈**：错误三分类（transient/permanent/fatal）+ 指数退避（base·2ⁿ，封顶 300s）+ 到期先探网（TCP 223.5.5.5/8.8.8.8/119.29.29.29），网不通顺延——休眠唤醒后不会送死

## 使用

```python
from task_runner import TaskProcessManager, TaskRunner, NetworkProbe

mgr = TaskProcessManager(".ai-team/runtime/taskmgr.db")

# 启动恢复：把上次猝死的任务翻出来（进程表里 RUNNING 且心跳超期）
for rec in mgr.recover_stale(stale_seconds=120):
    print("待恢复:", rec.id, rec.checkpoint.step)

mgr.register("T-002", "backend", {"lane": "account"})

def handler(ctx):
    ctx.step("scaffold", lambda: scaffold_service())      # 幂等：崩溃后不重跑
    rows = ctx.step("fetch_users", fetch_users)           # 每步立即落库
    ctx.save({"cursor": rows[-1].id})                     # 业务游标进检查点
    return {"users": len(rows)}

TaskRunner(mgr).run("T-002", handler)
```

CLI：

```bash
taskmgr register --id T-002 --kind backend --payload '{"lane":"account"}'
taskmgr checkpoint --id T-002 --step scaffold --data '{"ok":true}'
taskmgr recover --stale-seconds 120
taskmgr list --status retry_wait
taskmgr run --id T-002 --handler mymod:handler
taskmgr reset --id T-002        # DEAD 人工复位
```

## AI 团队接入约定（本仓库）

- 进程表位置：`.ai-team/runtime/taskmgr.db`（gitignore，纯运行时状态）
- 主理人派发 = `register`（task_id=工单号）；成员 HANDOFF = `complete`；成员失败通知 = `fail`；重启/恢复会话 = `recover` + 按 checkpoint 重新派发
- 多进程安全：WAL + busy_timeout=5s，成员各自 CLI 写入不互锁

## 测试

```bash
python -m pytest -q   # 24 passed：状态机/幂等/崩溃恢复(子进程 os._exit 模拟)/退避/探针
```

## 已知边界（诚实清单）

- SQLite 单机单文件：多机部署需换 Postgres 实现同接口（manager 已隔离存储细节）
- `step()` 缓存值经 JSON 规整，不可序列化对象退化为 repr
- 网络探测用公共 DNS/HTTPS 端点 TCP 连接，不验证业务可用性
- 退避抖动 `random.uniform(0.5,1.5)`：测试传 `jitter=False` 保证确定性
