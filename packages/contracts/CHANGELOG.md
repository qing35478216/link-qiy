# 契约变更日志

## v0.1.3（2026-10-14，调试窗端点补齐，工单 T-017）

> 版本顺序说明：v0.1.2 为 T-016 微信协议门修复（分支 fix/contract-v0.1.2，console-api 0.1.1→0.1.2）；本条目为契约包 v0.1.3，两分支合并后即形成连续序列。

来源：runtime-engineer T-004 交付时上报——对话引擎执行链已落库可回放，但 service-api 缺调试窗读端点，前端调试抽屉无契约可依。

**追加式端点（oasdiff 验证零 breaking）**：
- `service-api.yaml` 新增 `GET /v1/conversations`——会话列表（cursor 分页风格同 console-api：limit + cursor + nextCursor；按更新时间倒序）
- `service-api.yaml` 新增 `GET /v1/conversations/{conversationId}/events`——执行链事件回放（cursor 分页；元素为 `runtime-events.yaml` 的 `RuntimeEvent` 联合，含全部七类事件；可选 `traceId` 查询参数收窄到单次请求的执行链）
- 多租户经 API Key 归属限定（调用方不传 tenant）；跨租户/不存在会话 404 不暴露存在性
- 新增 `Conversation` schema；两个新端点均声明 401/404（events）/500 与 requestId 排障字段
- service-api 0.1.1 → 0.1.2；新增 `Conversations` tag（tag 列表改按字母序，spectral 规则要求）

**配套收紧**：
- `runtime-events.yaml` 七个事件 schema 的 `data` 升为 required（原为可选，生成 SDK 中事件负载全部可选、消费侧被迫写可选链）——纯预发布收紧，oasdiff 零 breaking；runtime-events 0.1.1 → 0.1.2
- `orval.config.ts` service 项目放行 `./runtime-events.yaml` 外部 $ref（orval v8 默认禁止，不放行则生成直接失败）

**SDK 同步**：`npm run generate` 重跑——sdk-ts 新增 `listConversations` / `listConversationEvents` 客户端方法、`Conversation` 及 RuntimeEvent 联合全部事件类型模型；sdk-py 不变（console-only 生成范围，T-001-sdk 决议）。

**下游注意**：runtime-engineer 需按本契约实现两端点（会话列表查询 + 事件序列查询，tenant 由 Key 归属限定）；前端调试抽屉消费 `@linkai/sdk-ts` 的 `getLinkAIServiceAPIOpenAI().listConversations/ listConversationEvents`。

## v0.1.1（2026-10-13，严明复审后修复，主理人代管——何约配额耗尽）

来源：qa-reviewer 合并后复审（门禁 3 PASS + 3 PARTIAL，3 BLOCKING + 11 NON-BLOCKING，工单 T-014）。

**BLOCKING 修复**：
- `runtime-events.yaml` 新增 `done` 终局事件（data: usage{promptTokens,completionTokens,totalTokens,credits} + finishReason + conversationId）——流式消费方以 done 为正常结束标志，连接关闭仅兜底（B1）
- `service-api.yaml` `stream` 默认值 `true` → `false`，对齐 OpenAI 惯例：不传该字段返回完整 JSON（B2，预发布行为变更，无外部消费者）
- `console-api.yaml` publish/unpublish summary 不再引用未定义的 AppPublished/AppUnpublished，改称"平台内部领域事件（v0.2 契约化）"（B3）

**安全与一致性修复**：
- `UserProfile` 的 id/plan/agreementAcceptedAt 标 `readOnly`——GET 仍返回，PATCH 生成类型排除，防客户端越权改套餐/协议时间（N7）
- 5 个公开登录端点补 `x-public: true`，与规则集豁免约定自洽（N3）
- `MessageChunkEvent.data.seq` 与 `EventEnvelope.conversationId` 升为 required（N9）
- `putAppConfig` description 写明全量替换语义（N6）
- 修 publish 响应描述残留撇号（N11）
- `ADOPTED-TOOLS.md` 勘误：orval 实际产物为 axios 客户端 + 类型 + MSW handlers，不含 TanStack Query hooks（N1）
- `README.md` 规则表 error-response 级别改回 warn，与 .spectral.yaml 一致（N2）

**SDK 同步**：`npm run generate` 重跑，sdk-ts/sdk-py 生成物随本版本更新（done 事件类型、stream 默认 false、UserProfile 只读字段、x-public 不影响生成物）。

**遗留**：N4/N5/N8/N10 进 T-015 积压（v0.2 冻结前处理）。

## v0.1.0（2026-10-13，Phase 0 冻结）

初始冻结，契约先行落地：

- `openapi/console-api.yaml` —— 管理面：账户域（微信扫码/手机号登录、JWT 刷新、协议勾选、个人信息）+ 应用域（应用 CRUD、轻量/知识库两类、配置七件套读写、公开开关、配置版本快照与回滚）+ 配额面板
- `openapi/service-api.yaml` —— 用户面（OpenAI 兼容）：POST /v1/chat/completions（stream SSE）、GET /v1/models、API Key 管理
- `openapi/runtime-events.yaml` —— SSE 事件协议：node_started / message_chunk / tool_called / thought / error / human_input_required 六类事件 + discriminator 联合
- `schemas/common.yaml` —— 复用片段：Error 信封（code/message/requestId）、TokenPair、Page（cursor 分页）、X-Tenant-Id 头

约定：错误模型统一 `{ code, message, requestId, details }`；列表统一 cursor 分页；kebab-case 路径 / camelCase 字段 / 复数资源名；多租户经 `X-Tenant-Id` 头（公开登录类端点以 `security: []` 显式豁免）。

已知留待 v0.2：工作流画布端点（node-registry 联动）、知识库管理端点（K-01~09）、计费/订单端点（B-04~06、R-01~03）、渠道管理端点（C-01~09）。

## 工具链（2026-10-13，T-001-sdk，不涉及契约变更）

- `scripts/generate.mjs` 实跑修复：orval v8 配置兼容；openapi-python-client 经 redocly bundle 单文件化（外部 `$ref` 会被静默跳过端点）后生成，`--overwrite` 支持重复运行
- 新增 `scripts/openapi-python-client.config.yaml`：默认包名取自 `info.title`（含中文），覆盖为 ASCII 安全的 `link_ai_console` / `link-ai-console-client`
- 产出：`packages/sdk-ts`（orval：console/service 双客户端 + 类型 + MSW handlers，axios 实例注入）、`packages/sdk-py`（openapi-python-client：httpx + pydantic v2）
