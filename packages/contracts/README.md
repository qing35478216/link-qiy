# packages/contracts — 单一事实源

API 契约唯一所有者：**契约工程师（contract-engineer）**。其他角色只读，不准直接修改。

- `openapi/console-api.yaml` — 管理面契约
- `openapi/service-api.yaml` — 用户面契约（OpenAI 兼容）
- `openapi/runtime-events.yaml` — SSE 事件协议
- `schemas/` — 复用 schema 片段
- `CHANGELOG.md` — 契约变更日志
- `scripts/generate.*` — sdk-ts / sdk-py 生成脚本

规则：契约先行；spectral lint + oasdiff 零 error 才可冻结；生成物 diff 必须干净。
