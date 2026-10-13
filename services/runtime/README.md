# services/runtime

应用运行时（对话引擎）——Phase 0 出口链路的最后一端：
登录✓ → 建应用✓ → 配模型提示词✓ → **对话** → 配额计费。

四层架构（api → services → domain ← infra，依赖只准向内；domain 零框架依赖）：

```
src/linkai_runtime/
├── api/         ① 接口层：FastAPI Router / 契约 DTO / 鉴权 / 序列化（只做协议转换）
├── services/    ② 应用层：ChatService 对话编排（装配→配额→模型→落库→事件流）
├── domain/      ③ 领域层：上下文装配纯函数 / Runtime Event 协议 / 会话·执行链模型（纯 Python）
└── infra/       ④ 基础设施层：SQLAlchemy 仓储 / model-proxy 客户端 / platform 客户端 / 配额
```

## 端点（契约 service-api.yaml v0.1.1）

| 端点 | 说明 |
|---|---|
| `GET /healthz` | 存活探针（不查依赖） |
| `POST /v1/chat/completions` | 对话补全。`stream=false`（**默认**）返回完整 JSON；`stream=true` 返回 SSE 事件流 |
| `GET /v1/models` | 可调用模型列表（透传 model-proxy） |

SSE 事件协议（runtime-events.yaml v0.1.1，七事件只增不改）：
`node_started → message_chunk*(seq 从 0) → done(usage{promptTokens,completionTokens,totalTokens,credits}+finishReason)`；
异常终局 `error(code/message/retriable)`。`tool_called/thought/human_input_required`
本期已实现协议构造器并有单测，主链路尚未产出（无插件/HITL 特性，Phase 1）。

## 本地开发

```bash
cd services/runtime
uv sync --all-extras
alembic upgrade head                       # 建表（启动不自动建表）
uv run uvicorn linkai_runtime.main:app --reload --port 8010
```

自验：

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src
uv run pytest                                # 领域层覆盖率 ≥70%（--cov-fail-under=70）
```

## 关键设计

1. **上下文装配是纯函数**（`domain/assembly.py`）：给定输入集合
   （应用设定 + 记忆轮次 + 知识库命中 + 本次问答 + 变量 + maxTokens 覆盖），
   输出确定。优先级：系统提示词 > 本次问答 > 知识库命中 > 记忆轮次；
   prompt 预算 = contextLength - maxTokens。单测全覆盖确定性/截断/溢出路径。
2. **stream 默认 false**：v0.1.1 契约明确修复点（对齐 OpenAI 惯例）。
3. **模型调用全走 model-proxy**（OpenAI 兼容端点 + X-Tenant-Id/X-Trace-Id 头），
   runtime 不直连厂商 SDK；计量 credits 以 model-proxy 回传 usage 为准。
4. **执行链落库**（`execution_traces`）：context_assembly / model_call 两步，
   plugin_name/thought/plugin_input/plugin_output/duration_ms/usage 全量落库，
   trace_id 贯通 OTel 约定（docs/observability.md §1.3 对话级 trace 可回放）。
5. **多租户**：Bearer API Key → tenant（铁律 6）；conversationId 续聊校验租户归属；
   全部查询带 tenant_id 过滤。

## 技术债（本期显式记录，均不影响出口链路）

| # | 技术债 | 现状 | 移除条件 |
|---|---|---|---|
| 1 | API Key 归属解析 | runtime 自有 `api_keys` 表（SHA-256 哈希 + 前缀，无明文）；platform Key 签发（service-api /api-keys 段）未实现 | platform 实现 Key 签发/解析后切 `PlatformApiKeyResolver`（HTTP），本表下线 |
| 2 | 应用设定来源 | 默认 static（env JSON 注入，tenant 维度不隔离）；`platform` 源已实现但依赖 platform 服务间端点（当前只有 console JWT 端点 → 502 APP_CONFIG_UNAVAILABLE） | platform 提供 `GET /internal/apps/{appCode}/runtime-profile`（X-Service-Token 鉴权）后切 platform 源 |
| 3 | 配额守卫 | 进程内存计数（单实例，重启清零，多副本不共享） | billing 服务落地后替换实现（端口 `QuotaGuard` 不变，services 零改动） |
| 4 | 知识库检索 | `NoopKnowledgeRetriever` 占位（配了知识库未命中 → missMessage 注记） | knowledge 服务落地后实现 `KnowledgeRetriever` 端口 |
| 5 | token 估算 | 启发式（CJK≈1/字、其余≈1/4字符），用于预算截断；计费用量用真实 usage | 按 model_code 分派 tiktoken（后续优化，见 ADOPTED-TOOLS.md） |
| 6 | 根 Makefile gate | 仍为 `TODO [T-004]` 占位（本工单领地仅 services/runtime/**，未改根文件） | 由 devops/主理人粘贴：`cd services/runtime && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src && uv run pytest` |
| 7 | 黄金集接入 | tests/golden-set 的 ModelRunner 接口已预留（走 /v1/chat/completions），但 runner 文件不在本工单领地，未接线；当前 9 条骨架用例 --validate-only 通过 | QA 侧接线（T-010 跟进单）+ 填满 20 条/框架 |

## 已知缺口（提缺陷单，不私改契约）

- **会话列表/执行链回放 API**：service-api.yaml 无 `GET /v1/conversations` /
  `GET /v1/traces/{id}`（调试窗需要）。契约新增必须走 T-001 流程。
- **引导问题**：来自应用设定 basic.guideQuestions（platform 已存），
  控制台调试页直读 platform 即可，runtime 无需端点。
