# LinkAI 可观测性约定（Phase 0 基线，所有服务必须遵守）

> 目标（docs/03 第六部分）：OTel trace 全链路（网关→服务→插件/模型）；结构化日志 trace_id 贯穿；
> 对话级 trace 可回放。本文是**约定文档**：服务脚手架已内置挂点，落地时引用本文即可。

## 1. Trace：OTel trace_id 强制贯通

### 1.1 何时必须带 trace_id（无例外）

| 场景 | 要求 |
|---|---|
| 所有入站 HTTP 请求 | 网关 / 各 FastAPI 服务自动插桩，trace 从入口创建 |
| 所有 AI 调用（model-proxy 及任何直连模型处） | 必须以 span 形式挂在当前 trace 下；模型厂商名/模型名/Token 用量进 span attributes |
| 所有外部请求（渠道 Webhook、支付、第三方 API、插件 gRPC） | 出站必须注入 `traceparent` header（W3C Trace Context），接收入站必须提取 |
| 所有计量/计费事件（billing、积分流水） | 事件体必须携带 `trace_id` 字段，用于对账与资损排查 |
| 异步任务（Celery） | 任务消息头携带 trace context，worker 侧续接同一 trace |

### 1.2 传递规范

- 格式：W3C Trace Context（`traceparent` / `tracestate` header），OTel SDK 默认实现，**禁止**自定义 header
- 服务间调用：走 `packages/sdk-py` 生成的客户端，SDK 内统一做 context 注入，业务代码不手写 header
- 渠道长连接（gateway WebSocket）：连接建立时绑定 trace，断线重连生成新 trace 并在日志标注关联

### 1.3 对话级 trace（继承 Dify/Langfuse 思路）

- 一次「用户消息 → 应用执行链 → 流式回复」= 一个 trace；每一步节点/检索/模型调用 = span
- 平台侧存储对话 trace 索引（应用 ID、会话 ID、trace_id 三元组），控制台调试页可跳转查看

## 2. 结构化日志格式

- 输出 JSON（生产/CI），本地开发可 `LOG_FORMAT=text`
- **每条日志必含**：`timestamp`（RFC3339 UTC）、`level`、`service`、`trace_id`、`span_id`、
  `msg`、`tenant_id`（多租户铁律 6：能取到必须打）
- Python：`structlog` + 从 OTel context 取 trace_id；Go：`slog` + OTel handler
- 日志中禁止出现：密钥/Token/用户隐私原文（脱敏后打 key 前缀即可）

```json
{"timestamp":"2026-10-13T07:00:00Z","level":"info","service":"linkai-model-proxy","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","tenant_id":"t-123","msg":"model call completed","provider":"openai","model":"gpt-4o","tokens":1520,"latency_ms":843}
```

## 3. 端点约定

| 端点 | 用途 | 约定 |
|---|---|---|
| `GET /healthz` | 存活探针 | 返回 `{"status":"ok"}`，**不查依赖**；compose healthcheck 与 K8s liveness 统一用它 |
| `GET /readyz` | 就绪探针 | 检查 DB/Redis 等关键依赖连通性；K8s readiness 用它 |
| `GET /metrics` | Prometheus 指标 | 进程就绪后暴露；至少含 RED 指标（Rate/Errors/Duration）+ 业务计量（token 消耗、队列深度） |

## 4. 落地挂点（Phase 0 已备好）

- 服务模板 pyproject 已带 `opentelemetry-sdk` + FastAPI 插桩依赖（`scripts/service-template/pyproject.toml`）
- 根 compose 暂不含 OTel Collector；本地用 stdout/OTLP 到 Jaeger，Collector + Grafana 进运行手册（Phase 2）
