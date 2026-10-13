# LinkAI 黄金评测集

AI **效果类**改动的回归护栏：改了 RAG 召回、提示词、模型路由、知识库切分，
输出质量会变，而这类改动**不会**让任何单测变红——只有跑分才知道。

规则（docs/03 第六部分 + 角色定义）：

1. 每框架 50 条，跨三大场景类：命理 / 客服 / 文档问答。
2. AI 效果改动**必须**跑分；分数跌超阈值卡 MR。
3. **黄金集分数连续两次下降 → 直接升级人类**（人类五检查点之一，效果问题可能是方向性的）。

## 目录

```
tests/golden-set/
├── README.md               # 本文件
├── SCORING.md              # 评分标准（工单验收标准 3 要求）
├── schema/
│   └── golden-case.schema.json   # 用例格式的 JSON Schema（唯一事实源）
├── cases/
│   ├── metaphysics.json     # 命理场景（骨架+ 样例）
│   ├── support.json         # 客服场景
│   └── docqa.json           # 文档问答场景
├── baseline/
│   └── baseline.json        # 基线分数（人工确认过的地板线）
└── run_golden_set.py        # 评分器（确定性打分，不依赖 LLM）
```

## 用例格式

由 `schema/golden-case.schema.json` 定义（JSON Schema 2020-12）。要点：

- `expect.mustInclude` / `mustNotInclude` —— 确定性断言，**无需 LLM 即可评分**。
  这是刻意的设计：黄金集要在 CI 里稳定跑，LLM-as-judge 有抖动，
  只对带 `expect.rubric` 的用例启用（那部分标记为「需人工确认」）。
- `expect.ranking` —— 多候选排序用例，算 nDCG / MRR。
- `tier` —— `smoke`（每次提交）/ `regression`（每日）/ `adversarial`（对抗）。

## 当前状态（Phase 0 / T-010）

**骨架 + 样例，尚未填满 50 条。** 这是刻意的：契约 v0.1.1 刚冻结，
runtime / knowledge / model-proxy 都还没落地，现在硬凑 50 条只能是编造的内容，
那样的「黄金集」比没有更危险——它会给出虚假的分数信号。

当前每类 3 条样例（含对抗用例），标`enabled: true`；其余 41 条待相应框架工单
（T-004runtime / T-006 提示词 / knowledge）落地后由该框架负责人填充。

**填满计划**（由各框架负责人在对应工单内完成，QA 只负责格式与门禁）：
- 命理 50 条：runtime 工单 + 命理框架负责人
- 客服 50 条：runtime + knowledge 工单
- 文档问答 50 条：knowledge 工单（依赖 RAG 落地才能造召回片段）

## 阈值策略

见 `baseline/baseline.json` 与 `SCORING.md`。核心规则：
- 单次跌幅 ≤ 2%：warn，记录，不卡 MR。
- 单次跌幅 > 5%：FAIL，卡 MR。
- **连续两次下降**：无论幅度，升级人类（QA 不得自行判断「可以接受」）。

## 运行

```bash
# 只跑 smoke 层（CI 必跑，快）
tests/golden-set/run_golden_set.py --tier smoke

# 跑全量并与基线比对（出报告）
tests/golden-set/run_golden_set.py --all --compare-baseline

# 校验所有用例符合 schema（格式回归）
tests/golden-set/run_golden_set.py --validate-only
```

> `--validate-only` 不需要任何模型或服务，纯 schema 校验，CI 必跑。
> 这条能防住「有人手写了个格式不对的用例，评测跑分时才炸」的情况。