# packages/contracts — 单一事实源

API 契约唯一所有者：**契约工程师（contract-engineer）**。其他角色只读，不准直接修改。

- `openapi/console-api.yaml` — 管理面契约
- `openapi/service-api.yaml` — 用户面契约（OpenAI 兼容）
- `openapi/runtime-events.yaml` — SSE 事件协议
- `schemas/` — 复用 schema 片段
- `CHANGELOG.md` — 契约变更日志
- `scripts/generate.*` — sdk-ts / sdk-py 生成脚本

规则：契约先行；spectral lint + oasdiff 零 error 才可冻结；生成物 diff 必须干净。

## 本地校验（spectral）

契约改完先本地跑一遍再提 PR：

```bash
cd packages/contracts
npm install          # 首次
npm run lint         # error 级拦截，日常 PR 用这个
npm run lint:strict  # warn 级也拦截，冻结契约前用这个
```

`openapi/` 与 `schemas/` 为空时脚本会跳过（退出码 0），契约落地后自动恢复严格门禁。

规则集在 `.spectral.yaml`，基于 `spectral:oas` 扩展。项目定制规则统一以 `linkai-` 开头：

| 规则 | 级别 | 约束来源 |
|------|------|----------|
| `linkai-operation-id-exists` / `-casing` | error / warn | 生成物命名可控（契约先行） |
| `linkai-tenant-context-declared` | warn | 架构铁律 #6 多租户穿透 |
| `linkai-error-response-4xx` / `-5xx` | error | 客户端可穷举失败分支 |
| `linkai-error-envelope-shape` | error | 统一错误信封 `{code, message, requestId}` |
| `linkai-security-defined` | error | 架构铁律 #5 安全基线 |
| `linkai-path-kebab-case` / `-summary-required` / `-tags-required` | warn | 可维护性 |
| `linkai-deprecation-has-sunset` | error | 破坏性变更可排期 |

**公开接口豁免**：确属公共服务的（健康检查、登录、定价页），在 operation 上写 `x-public: true`，
tenant 规则即跳过。豁免必须显式，不接受默认放开。

## 契约冻结门禁（gate）

```bash
npm run gate   # = lint（spectral）+ diff（oasdiff），两者零 error 才可冻结
```

- `npm run lint` — spectral 管「写得规不规范」，规则见上
- `npm run diff` — oasdiff 管「改得兼不兼容」：对比工作区契约 vs `git HEAD`，
  检出破坏性变更即失败，要求升版本号并在 `CHANGELOG.md` 写迁移说明；
  新增文件自动跳过。也可手动比对：`npm run diff -- <base.yaml> <revision.yaml>`

> `oasdiff` 是独立 Go 二进制，需随开发环境预装。未装时 `diff` 脚本会打印安装命令并失败，
> 不会静默放过。

**已知坑（写在这里防止复踩）**：`oasdiff breaking` 默认退出码恒为 0
（`--fail-on` 默认 NONE），直接拿它当门禁会「检出问题却不拦截」。
脚本里已显式加 `--fail-on ERR`。
