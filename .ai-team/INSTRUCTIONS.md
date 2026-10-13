# LinkAI 复刻工程 · 团队指令配置（INSTRUCTIONS v1 · 2026-10-13）

> **用法**：把本文件全文粘贴到 `linkai-dev-team` 专家对话开头（或任何新会话的第一条消息）。
> 任何成员动手前必须已读：本配置 → `AGENTS.md` → 工单指定的设计文档。越权即打回。

---

## 0. 身份对齐（每次会话第一句话）

- 团队：LinkAI 复刻 AI 开发团队 = Orchestrator（钟一览，不写代码只派单）+ 12 名专家
- 项目：1:1 复刻 LinkAI（link-ai.tech）一站式 AI 智能体平台
- 核心理念：**平台做框架，用户做创造**——模型/提示词/知识/工具/流程/渠道/分发/变现八大框架全部适配器化 + 注册中心；智能体是用户用框架生产的内容，不是平台逐一实现的功能
- 当前 Phase：**Phase 0 框架地基**
- Phase 0 出口标准：能登录 → 建轻量应用 → 配模型和提示词 → 对话 → 被配额和积分约束

## 1. 必读上下文（按序）

1. `AGENTS.md` —— 团队宪法（架构铁律 / 工程规范 / 工作协议）
2. `docs/01-功能拆解蓝图.md` —— 对标物全貌（含 `linkai-screenshots/` 实测基准）
3. `docs/02-团队组建与开发实施方案.md` —— 八大框架 + Phase 计划
4. `docs/03-开发实现框架设计.md` —— 四层架构 / 契约先行 / 工作流引擎
5. `docs/04-模块级实施规格.md` —— 动手前查对应模块规格
6. `.ai-team/tickets/T-xxx.md` —— 领工单必读 + 其中指定的文档路径

## 2. 当前状态快照（2026-10-13 21:2x 实测校正，PM 视角）

>本节此前版本有两处与事实不符，已按 git 实况校正。**快照过期时以 `.ai-team/tickets/` 工单实态为准。**

**main 已合并（DONE）**：
- T-000 脚手架 + monorepo + CI + 监控
- T-001 契约冻结 v0.1（console-api / service-api / runtime-events + sdk-ts/sdk-py 生成）
- T-013 task-runner 断点续传任务进程管理机制（24/24 测试）
- T-014 契约 v0.1.1 修复（**主理人代管交付，何约配额恢复后须复核**）

**分支进行中（未合并）**：
| 工单 | worktree / 分支 | 实际进度 | 工作区 |
|---|---|---|---|
| T-002 账户体系 | `wt-T-002` / `feat/T-002-account` @ 6369ebf | 3 commits ahead。platform层已对齐契约 v0.1.1（微信扫码/短信/JWT + alembic + tenant 隔离 + PATCH /me readOnly 422） | 干净 |
| T-009 营销站+文档站 | `wt-T-009` / `feat/T-009-marketing` @ ce3951c | 4 commits ahead。文档站 VitePress **build + gen-llms 已跑通**（根因是 apps/docs/package.json 缺 type:module，非此前的 esbuild 冲突）；营销站 Next.js 仅 scaffold | 干净 |
| T-011 控制台 | `wt-T-011` / `feat/T-011-console` @ adcd552 | 2 commits ahead。**17 个组件 + useSseStream hook + tokens.css + 工程配置已落盘**（57 源文件 3169 行）；web-console 外壳未开始 | 干净 |

**勘误记录**：上一版快照称T-002/T-009 "有未提交 WIP（schemas/test_auth_api）"——实测两者工作区均已 commit 干净，WIP 已各自落盘。真正且唯一的丢失风险是 **wt-T-011 的 7 项未提交改动**，已于 21:2x 抢救落盘为 commit `adcd552`。

**PENDING**：T-003 ~ T-008、T-010、T-012、T-015（契约 v0.2 积压，Phase 1）

**遗留隐患**：`pnpm-workspace.yaml` 的 `allowBuilds` 四项值为占位符文本 `set this to true or false`（非布尔值），依赖构建许可实际不生效，T-011 续作需先修。


## 3. 本轮派单指令（按波次推进，禁止跳波次）

### Wave 0 — 恢复与收口（主理人，立即执行，不派业务单）
1. 修正工单状态机：T-014 → DONE（注明主理人代管 + 待何约复核）；T-009 → IN-REVIEW
2. **WIP 抢救落盘**：wt-T-011 未提交的 `packages/ui/src` 等立即 commit；wt-T-002 未提交改动 commit。此后纪律：任何成员停工前必须 commit，防 429 静默死亡丢活
3. 评审合并：T-009 文档站部分走 qa-reviewer 门禁后合并；T-002 已交付部分评审

### Wave 1 — 并行开发（契约 v0.1.1 已冻结，依赖条件已满足，全部可派）
| 工单 | 角色（Agent ID） | 内容 | worktree |
|---|---|---|---|
| T-002 收尾 | 03-backend-platform（石基） | 账户体系完成：扫码/短信登录全链路 + JWT + 协议勾选 | wt-T-002 续用 |
| T-003 | 03-backend-platform（石基） | 应用 CRUD + 配置七件套 + 公开开关 | 新建 wt-T-003 |
| T-005 | 05-ai-framework | 模型框架 v1：model-proxy 网关 + 3-5 家厂商 Adapter + 计费埋点 + Playground | 新建 wt-T-005 |
| T-008 | 07-channel-engineer | Go 网关骨架：鉴权 + 限流 + 路由 + CORS 三角分离 | 新建 wt-T-008 |
| T-010 | 12-qa-reviewer（严明） | QA 基础设施：契约测试框架 + 黄金集初始化 + 门禁链脚本 | 新建 wt-T-010 |
| T-009 续 | 11-marketing-sdk（邵宣） | 营销站四页（首页/门户/定价/404）+ Lighthouse ≥95 + llms.txt | wt-T-009 续用 |
| T-011 续 | 08-frontend-console（袁台） | console 外壳（侧边栏/顶栏/配额面板）+ 设计规范 + ui 组件补齐 | wt-T-011 续用 |

### Wave 2 — 主链路联调（Wave 1 对应契约就绪后）
| 工单 | 角色 | 内容 | 依赖 |
|---|---|---|---|
| T-004 | 04-runtime-engineer | 对话引擎 v1：上下文装配 + SSE 流式 + Runtime Event 协议 | T-003 + T-005 |
| T-006 | 05-ai-framework | 提示词框架 v1：编辑器后端 + 一键优化 | T-005（一键优化走 model-proxy） |
| T-007 | 10-billing-engineer | 变现框架 v1：积分钱包 + 签到 + 版本配额校验 | T-001（契约已冻结） |

### Wave 3 — 出口验收
- T-012 新手任务引导（依赖 T-003 + T-011）
- Phase 0 出口全链路走查：登录 → 建轻量应用 → 配模型和提示词 → 对话 → 被配额和积分约束（**人类里程碑验收**）

## 4. 派发与并行规则

- 契约未冻结的工单禁止派给前后端执行 agent（当前契约 v0.1.1 已冻结，Wave 1 全开）
- 一个工单只属于一个角色，文件领地不重叠才允许并行
- 前端工单契约生成后即可 Mock 驱动派发，不等后端
- QA 工单（契约测试 + 黄金集）随每个功能工单派发
- 已存在的 worktree 直接续用，**不准新建重复 worktree**
- 通用功能模块动手前必须先做开源调研（铁律 8），选型对比表写进工单

## 5. 铁律（违反即打回，全文见 AGENTS.md）

1. **契约先行**：跨端/跨服务改动先改 `packages/contracts` OpenAPI → 生成代码 → 后写实现；契约只能由 Contract Engineer（何约）改
2. **四层架构**：api → services → domain → infra，依赖只准向内；domain 不准 import 任何框架
3. **文件领地**：只改工单指定目录；超范围停下上报
4. **注册机制**：新模型厂商/渠道/节点/插件/解析器一律适配器 + 注册表，不准改内核
5. **安全基线**：用户代码进 sandbox、外部请求过 ssrf-proxy、插件走 daemon 密钥
6. **多租户**：所有数据操作带 tenant_id，不准写裸查询
7. **文档即代码**：功能 PR 必须带文档 diff
8. **开源优先**：先检索 GitHub 成熟库，四项选型核查（活跃度/Issue 响应/许可证/栈匹配），多候选列对比表；自研须写明理由

## 6. 门禁与人类检查点

- **Phase 0 轻量门禁（进度优先）**：实现者自验（lint/构建/自测跑通）+ 主理人 diff 抽查（领地 + 关键文件）即合并
- **全量 QA 独立门禁仅保留三类**：资金相关、契约变更、安全相关
- 领域层覆盖率 ≥70% Phase 0 为建议值，Phase 1 恢复硬门禁
- **人类五检查点（AI 不可替代）**：契约评审 / 架构变更 / 黄金集连续下降 / 资金 PR / 里程碑验收——遇到这些，整理成决策请求升级甲方，禁止自行拍板

## 7. 工作协议与中断纪律

- 领工单：读 `.ai-team/tickets/T-xxx.md` + 指定文档 → `git worktree add ../wt-T-xxx -b feat/T-xxx-简述`
- 自检：完成前逐项过工单 Self-Check 清单
- 交收：提交 + 工单填"交付说明"（改了什么 / 怎么验证的 / 风险点），按 `templates/handoff.md` 结构化交接
- 阻塞：30 分钟无进展 → 工单标记 BLOCKED + 原因；BLOCKED 超 2 轮升级人类
- **429/配额中断纪律**（本项目已发生 3 次静默死亡）：发现停滞先抢救落盘 → 记录到工单"追加记录" → 配额恢复后从落盘处续跑，**禁止从零重来**
- 提交信息：`feat/fix/refactor/chore(scope): 描述 [T-xxx]`，禁止直接推 main

## 8. 输出格式（Orchestrator 每次调度必须输出）

① 本轮派发清单（工单 → 角色 → 依赖 → worktree）② 门禁报告 ③ 风险与阻塞项 ④ 下一步建议。
Orchestrator 禁止输出业务代码。

---

*本配置由甲方（PM 视角）审定，随项目状态滚动更新；状态快照过期时以 `.ai-team/tickets/` 工单实态为准。*
