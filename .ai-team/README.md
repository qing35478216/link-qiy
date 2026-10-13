# .ai-team — AI 开发团队工作区

本目录是 AI 开发团队（Orchestrator + 11 名专家）的协作工作区，与仓库一起版本化管理。

## 目录结构

```
.ai-team/
├── INSTRUCTIONS.md   # 团队常驻指令配置（粘贴到专家对话开头，含状态快照+派单波次+铁律）
├── roles/           # 12 个角色提示词（工具无关通用版，供 Codex/Claude Code/Cursor 等外部智能体使用）
│   ├── 01-orchestrator.md          # 总编排
│   ├── 02-contract-engineer.md     # 契约工程师
│   ├── 03-backend-platform.md      # 平台后端
│   ├── 04-runtime-engineer.md      # 运行时
│   ├── 05-ai-framework.md          # AI 框架（模型/RAG/提示词）
│   ├── 06-workflow-engineer.md     # 工作流引擎
│   ├── 07-channel-engineer.md      # 渠道网关
│   ├── 08-frontend-console.md      # 控制台前端
│   ├── 09-canvas-engineer.md       # 画布
│   ├── 10-billing-engineer.md      # 计费
│   ├── 11-marketing-sdk.md         # 营销站与 SDK
│   └── 12-qa-reviewer.md           # 测试评审
├── templates/       # 工单模板 + 交接消息模板
├── tickets/         # 工单队列（T-xxx.md，Phase 0：T-000 ~ T-012）
└── local/           # 本地临时产物（git 忽略）
```

## 工作协议

1. **派发**：Orchestrator 把 Phase 任务拆成工单写入 `tickets/T-xxx.md`（关联功能 ID + 契约版本 + 文件领地 + 验收标准 + Self-Check）
2. **执行**：专家成员领工单 → `git worktree add ../wt-T-xxx -b feat/T-xxx-简述` → 只改领地内文件 → 过 Self-Check
3. **交接**：按 `templates/handoff.md` 结构化交接（状态/产出/验证证据/下游注意/风险），无"下游注意"字段的交接视为无效
4. **门禁**：qa-reviewer 跑门禁链（diff 领地检查 → lint/type → 单测覆盖率 ≥70% → 契约测试 → 黄金集跑分 → 架构守卫评审）
5. **升级**：BLOCKED 超 2 轮 / 架构歧义 / 契约冲突 / 黄金集连续下降 / 资金 PR → 升级人类

## 与 WorkBuddy 专家团的关系

WorkBuddy 专家中心已注册同名团队专家 **linkai-dev-team**（LinkAI 复刻 AI 开发团队），成员与本目录角色一一对应。在 WorkBuddy 内直接对话专家团即可调度；本目录角色文件供外部编码智能体（Codex / Claude Code / Cursor）按 7.1 节配置使用。
