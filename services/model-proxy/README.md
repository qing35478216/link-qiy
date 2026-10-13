# services/model-proxy — 模型框架

统一 OpenAI 兼容网关 + 厂商 Adapter 注册机制 + 降级链 + token 计量埋点 + Playground。

领地：AI 框架工程师（ai-framework）。工单 T-005。

## 核心理念

**平台做框架，用户做创造。** 新接一家模型厂商 = 写一个适配器 + 注册表加一行，
**内核（domain/services/api）零改动**。这条约束由 `tests/unit/test_registry.py`
与 `test_architecture_guard.py` 的 AST 守卫测试强制——有人后来写
`if provider == "openai"` 到内核里，CI 会直接红。

## 端点

| 方法 | 路径 | 契约 | 说明 |
|---|---|---|---|
| POST | `/v1/chat/completions` | service-api.yaml v0.1.1 | `stream=true` 按 runtime-events 出 SSE |
| GET | `/v1/models` | service-api.yaml v0.1.1 | 可调用模型（含价格/能力/上下文长度） |
| POST | `/_internal/playground/completions` | 契约缺口，见 T-005 §5-2 | Playground 试玩 |
| GET | `/_internal/playground/models` | 契约缺口 | Playground 模型下拉 |
| GET | `/healthz` | — | K8s 探针 |
| GET | `/healthz/providers` | — | 注册中心自省（铁律 4 的可观测证据） |
| GET | `/playground` | — | Playground 最小可用页面 |

鉴权：网关注入 `X-Tenant-Id` / `X-Trace-Id`。**model-proxy 不自行校验用户 API Key**
（Key 签发归 platform，跨服务禁止直接查库）。

## 已接入厂商

| 厂商 | provider | 协议 | 备注 |
|---|---|---|---|
| OpenAI | `openai` | OpenAI 兼容 | |
| Anthropic | `anthropic` | **原生 Messages** | 需 6 处协议翻译，单独实现 |
| DeepSeek | `deepseek` | OpenAI 兼容 | reasoner 模型剔除采样参数 |
| 通义千问 | `qwen` | OpenAI 兼容 | `compatible-mode/v1` |
| 智谱 GLM | `glm` | OpenAI 兼容 | `api/paas/v4` |

**统一走 OpenAI 兼容 HTTP，不引入任何厂商 SDK**（许可证/体积/维护成本考量，
全文见 `ADOPTED-TOOLS.md`）。

## 架构

四层，依赖只准向内（`docs/03` §3.1）：

```
api/        协议转换（FastAPI，只做 DTO ↔ 领域对象）
services/   应用编排（网关用例、Playground）
domain/纯 Python 零框架：适配器协议、注册中心、降级链、计量
infra/      SSRF 闸门、出网客户端、厂商适配器、内存端口实现
```

铁律落点：

- **铁律 4**：加厂商只动 `infra/adapters/` + `BUILTIN_ADAPTERS` 一行；
- **铁律 5**：所有出网强制经 `infra/http_client.py` + `infra/ssrf.py`，
  AST 守卫禁止适配器直接 import httpx；
- **铁律 6**：`ModelCatalog` / `CredentialResolver` 协议签名强制带 `tenant_id`，
  `MeteringEvent` 构造校验非空；
- **红线（不绕计量）**：`ModelInvocationService` 是唯一持有 `AdapterRegistry` 的地方，
  api 层拿不到注册表，物理上杜绝绕过。成功与失败**都**发计量事件。

## 本地运行

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"

# 平台厂商 Key（按需，至少配一个）
export LINKAI_PROVIDER_KEY_DEEPSEEK=sk-xxx

.venv/bin/uvicorn linkai_model_proxy.api.app:app --port 8100
# Playground: http://127.0.0.1:8100/playground?tenant=dev-tenant
# 接口文档:   http://127.0.0.1:8100/docs
```

## 门禁

```bash
.venv/bin/ruff check .            # lint
.venv/bin/ruff format --check .  # format
.venv/bin/black --check .        # 双保险
.venv/bin/mypy                   # --strict
.venv/bin/python -m pytest       # 含 domain 覆盖率门禁（≥70%）
```

测试**零触网**：`tests/conftest.py` 的 autouse 护栏在 socket 层拦截真实出网，
厂商响应全部用 respx 回放。

## Phase 0 用内存实现的部分

`infra/memory.py` 的三个端口实现（目录 / 凭证 / 计量）按 domain `Protocol` 编程，
Phase 1 换 Redis / MQ / PostgreSQL **不改业务代码**：

| 当前（内存） | 计划替换 | 阻塞方 |
|---|---|---|
| `InMemoryTelemetrySink` | MQ → billing 原子扣减 | **T-007 依赖** |
| `InMemoryCredentialStore` | KMS / Vault 或 DB 加密列 | — |
| `InMemoryModelCatalog` | PostgreSQL（全部带 tenant_id） | — |
| 本地 SSRF 校验 | 走 `ssrf-proxy` 服务 | **T-008**（需对齐判定规则） |

## 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `LINKAI_PROVIDER_KEY_{PROVIDER}` | 空 | 平台公共 Key，PROVIDER ∈ openai/anthropic/deepseek/qwen/glm |
| `LINKAI_SSRF_ALLOWED_HOSTS` | 内置 5 家 + `*.bigmodel.cn` | 出网白名单（逗号分隔，支持 `*.suffix`） |
| `LINKAI_SSRF_ALLOW_HTTP` | `false` | 开发态放开 http；**生产必须 false** |
| `LINKAI_HTTP_CONNECT_TIMEOUT` | `5` | 连接超时（秒） |
| `LINKAI_HTTP_READ_TIMEOUT` | `60` | 读超时（秒） |
| `LINKAI_RETRY_BACKOFF_MS` | `200` | 同模型重试的指数退避基数 |

> 内置模型价格与上下文长度为厂商公开文档量级值，**上线前须人工核对最新价目**
> （价格错 = 直接算错账）。
