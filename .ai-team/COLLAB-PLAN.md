# LinkAI 复刻工程 · 协同计划（2026-10-13 Wave 0 收口后）

> 本文件由主理人（Orchestrator）维护，记录当前协同态势与派单实况。
> 权威依据优先级：`.ai-team/tickets/` 工单实态 > 本文件 > INSTRUCTIONS.md 快照。

## 一、协同机制

- 团队：`linkai-dev-team`，主理人 1 + 执行专家 6（本轮已派）
- 任务板：16 项，按 Wave 分层，依赖用 blockedBy 固化
- 铁律：Orchestrator 不写业务代码，只派单、收口、把关

## 二、Wave 0 收口结果（已完成）

| 项 | 结果 |
|---|---|
| T-011 WIP 抢救 | ✅ 7 项未提交改动落盘为 `adcd552`（63 files / +4851，57 源文件 3169 行） |
| 工单状态机校正 | ✅ T-014→DONE、T-009→IN-REVIEW、T-002→IN-REVIEW、T-011→IN-PROGRESS |
| T-009 文档站合并 | ✅ 合并 main @ `db78a63`，主理人独立复验 build 4.33s / 13 页面 / llms.txt 12 条 |

### 三处实测勘误（原记录与事实不符）

1. **INSTRUCTIONS.md 快照过期**：称 T-002/T-009「有未提交 WIP」，实测两者工作区均已干净。真正且唯一的丢失风险是 wt-T-011 的 7 项改动。
2. **T-009 根因误判**：原记「esbuild 版本冲突致 vitepress build 失败」——证伪。真实根因是 `apps/docs/package.json` 缺 `"type": "module"`，Vite 以 CJS 捆绑 config 时 require ESM 失败。
3. **T-011 进度误判**：原记「仅包骨架」，实测 17 个组件 + SSE hook + tokens + 工程配置已落盘，只是未提交未回传。

### 遗留隐患

- `pnpm-workspace.yaml` 的 `allowBuilds` 四项值为占位符文本 `set this to true or false`（非布尔值），依赖构建许可不生效 → 已交 T-011 续作修复
- T-009 `gen-llms` 会产出 `apps/docs — 文档站` 这类目录名派生条目，标题提取逻辑待优化

## 三、Wave 1 派单实况（6 单并行）

| 工单 | 执行者 | 领地 | worktree | 门禁 |
|---|---|---|---|---|
| T-010 QA 基础设施 | qa-reviewer（严明） | QA 框架/门禁脚本 | 新建 wt-T-010 | 基础单 |
| T-008 Go 网关骨架 | channel-engineer | `services/gateway/` | 新建 wt-T-008 | **安全类·独立门禁** |
| T-005 模型框架 v1 | ai-framework | `services/model-proxy/` | 新建 wt-T-005 | 轻量门禁 |
| T-011 控制台续作 | frontend-console（袁台） | `apps/web-console/`、`packages/ui/` | 续用 wt-T-011 | 轻量门禁 |
| T-009 营销站续作 | marketing-sdk（邵宣） | `apps/web-marketing/` | 续用 wt-T-009 | 轻量门禁 |
| T-002 账户体系收尾 | backend-platform（石基） | `services/platform/src/**`（账户域） | 续用 wt-T-002 | 轻量门禁 |

### 串行约束（派单时发现，原指令未标明）

**T-002 与 T-003 领地完全重叠**——两者文件领地都是 `services/platform/src/**`，且同属 backend-platform 角色。违反铁律 3（文件领地）与并行规则「领地不重叠才允许并行」。

处置：T-003 改为 **T-002 收尾后串行开工**，已用 blockedBy 固化到任务板。原指令把两单同列 Wave 1 属安排失误，已修正。

## 四、门禁分级（Phase 0 轻量门禁 · 进度优先）

| 类型 | 门禁 | 本轮适用工单 |
|---|---|---|
| 资金相关 | 全量 QA 独立门禁 + **双人评审** | T-007（Wave 2） |
| 契约变更 | 全量 QA 独立门禁 | 暂无 |
| 安全相关 | 全量 QA 独立门禁 | **T-008** |
| 其余 | 实现者自验 + 主理人 diff 抽查即合并 | T-002/T-005/T-009/T-010/T-011 |

领域层覆盖率 ≥70% 在 Phase 0 为建议值，Phase 1 恢复硬门禁。

## 五、Wave 2 / 3（待前置就绪）

| 工单 | 执行者 | 依赖 |备注 |
|---|---|---|---|
| T-004 对话引擎 v1 | runtime-engineer | T-003 + T-005 | 出口链路「对话」环节 |
| T-006 提示词框架 v1 | ai-framework | T-005 | 与 T-005 **同角色，必须串行**；一键优化走 model-proxy |
| T-007 变现框架 v1 | billing-engineer | T-001（**已满足**） | 实为可提前开工，资金类需双人评审 |
| T-012 新手任务引导 | frontend + backend 联合 | T-003 + T-011 | 需先明确领地切分 |
| Phase 0 出口验收 | **人类** | 全部 | 登录→建应用→配模型提示词→对话→被配额积分约束 |

T-007 依赖虽已满足但排在 Wave 2 —— 是否前移到 Wave 1 以压缩关键路径，**待人类决策**。

## 六、人类检查点（AI 不可替代）

1. **契约评审** —— T-005 若发现契约缺口，禁止自改，上报
2. **架构变更** —— 偏离 docs/01~03 的决策
3. **黄金集分数连续下降** —— T-010 建立后启用
4. **资金相关 PR** —— T-007 需双人评审
5. **里程碑验收** —— Phase 0 出口

**待甲方决策事项**：
- T-007 是否前移 Wave 1（压缩关键路径）
- T-005 厂商 SDK 许可证风险（GPL/AGPL 或非商用许可需人类确认，建议优先 OpenAI 兼容 HTTP 接口）
- Phase 0 出口验收需至少一家可用模型厂商 API Key，请确认甲方已准备
- T-014 何约复核时点

## 七、中断纪律（本项目已 3 次静默死亡）

**任何成员停工前必须 `git add -A && git commit`**，宁可提交标注 WIP 的半成品。配额恢复后从提交处续跑，禁止从零重来。已在全部派单 prompt 中显式写入。

---

## 五、Wave 1 增补（2026-10-13 21:40）

### T-002 收口合并 ✅
- feat/T-002-account @ 6369ebf 已合并 main（`b376b3b`，解决 T-002.md 一处冲突：取石基 DONE 版本，b7a7752 的 IN-REVIEW 记录被实际合并取代）
- **主理人独立复跑确认**（非采信报告）：pytest 全过 + 域覆盖 99.48%、mypy --strict 31 文件零问题、ruff 全过、53 文件领地零越界
- 复验环境坑（已入记忆）：platform venv 需 `uv sync --all-extras`（dev extras 含 pytest/httpx）；pytest 须用 `.venv/bin/python -m pytest`（`uv run pytest` 会解析到错误环境）；沙箱拦 pytest tmp_path → `--basetemp=/tmp/xxx`

### T-003 派单（串行解阻）
- COLLAB-PLAN 发现的 T-002/T-003 领地完全重叠约束生效：T-002 合并后 T-003 立即派石基（推荐新分支 feat/T-003-apps）
- 派单要点已传达：七件套 PUT 全量替换语义（v0.1.1 契约）、publish 不发未定义事件（内部 MessageBus）、quota/summary 的 walletBalance 占位 0

### Wave 2 预览（T-005 落地后）
- T-004 运行时引擎（刘畅）：排在 T-005 model-proxy 之后，避免集成返工；事件协议 v0.1.1 的 done 终局事件已就位
- T-006 提示词框架（艾枫，model-proxy 同服务内）、T-007 计费（钱保）：Wave 2/3
- 严明 T-010、渠畅 T-008 在途（worktree 已建，等回传）

### 工程卫生
- task-runner flaky 测试修复：test_due_retries 原假设退避恒 2s，实际带抖动（1~3s）→ 改为睡到记录自身的 next_retry_at；24/24 绿
- `LinkAI复刻工程文档/`（用户原始文档副本，与 docs/ 重复）已 gitignore，不删用户文件
