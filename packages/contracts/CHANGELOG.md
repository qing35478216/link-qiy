# 契约变更日志

## v0.1.0（2026-10-13，Phase 0 冻结）

初始冻结，契约先行落地：

- `openapi/console-api.yaml` —— 管理面：账户域（微信扫码/手机号登录、JWT 刷新、协议勾选、个人信息）+ 应用域（应用 CRUD、轻量/知识库两类、配置七件套读写、公开开关、配置版本快照与回滚）+ 配额面板
- `openapi/service-api.yaml` —— 用户面（OpenAI 兼容）：POST /v1/chat/completions（stream SSE）、GET /v1/models、API Key 管理
- `openapi/runtime-events.yaml` —— SSE 事件协议：node_started / message_chunk / tool_called / thought / error / human_input_required 六类事件 + discriminator 联合
- `schemas/common.yaml` —— 复用片段：Error 信封（code/message/requestId）、TokenPair、Page（cursor 分页）、X-Tenant-Id 头

约定：错误模型统一 `{ code, message, requestId, details }`；列表统一 cursor 分页；kebab-case 路径 / camelCase 字段 / 复数资源名；多租户经 `X-Tenant-Id` 头（公开登录类端点以 `security: []` 显式豁免）。

已知留待 v0.2：工作流画布端点（node-registry 联动）、知识库管理端点（K-01~09）、计费/订单端点（B-04~06、R-01~03）、渠道管理端点（C-01~09）。
