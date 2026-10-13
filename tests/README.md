# tests/ —— QA 基础设施（T-010）

三条护栏。每条都对应一类「不跑就出事」的风险：

| 目录 | 护的是什么 | 什么时候必须跑 |
|---|---|---|
| `contracts/` | 服务实现 / 生成物 vs 冻结契约漂移 | 每次提交（消费者侧）；契约或服务变更时加跑提供者侧 |
| `golden-set/` | AI 效果回归（RAG / 提示词 / 模型路由） | 效果类改动；每日回归 |
| `gate/` | 分级门禁编排 + 文件领地 + 架构铁律机检 | 每个 PR 合并前 |

## 一条命令跑全部门禁

```bash
python3 tests/gate/gate_chain.py --base main
```

输出分级报告 + PASS/FAIL + 不通过原因。退出码 0/1 可直接接CI。

> **门禁入口就是上面这个文件。不存在 `test_gate.py`。**
> 若你在别处看到提到 `test_gate.py` 或「门禁入口文件」的，那是误传——
> 该文件在本仓库 git 全历史中从未存在过。

## 分级逻辑（AGENTS.md Phase 0 轻量门禁）

```
变更路径/内容 → 风险类别 → 该跑哪些检查
     ├─ 资金相关 → 全量独立门禁 + 双人评审（人类检查点）
     ├─ 契约变更 → 全量独立门禁 + 契约评审（人类检查点）
     ├─ 安全相关 → 全量独立门禁 + 安全评审
     └─ 其余     → Phase 0 轻量门禁：实现者自验 + 主理人 diff 抽查
```

领域层覆盖率 ≥70% 在 Phase 0 是**建议值**，脚本只报不卡（Phase 1 恢复硬门禁）。

## 三条不可妥协的语义

1. **SKIP ≠ PASS**。spectral 未装、oasdiff 未装、服务未起→ 报告标 SKIP 并说明原因。
   「没跑」不等于「跑过了」，这是本项目反复踩的坑（T-013 以来3 次静默死亡）。
2. **缺口基线只减不增**。Phase 0 经甲方指令降级的契约规则登记在
   `contracts/known_gaps.py`，存量缺口不阻塞，**新增缺口立即 FAIL**。
3. **脚本不能替人签字**。即使门禁全绿，涉及资金/契约/安全的改动仍需对应人类检查点确认。

## 首次使用

```bash
# 契约测试（Python）
uv venv tests/contracts/.venv --python 3.13
uv pip install --python tests/contracts/.venv/bin/python -r tests/contracts/requirements.txt

# Node 侧（契约 lint 需要）
pnpm install
```

详见 `contracts/README.md`。

## 给其他工单的使用说明

- **T-003 / T-005 / T-008**（应用 CRUD / 模型框架 / 网关）：服务起好后设
  `LINKAI_BASE_URL` / `LINKAI_TEST_TOKEN` / `LINKAI_TEST_TENANT_ID`，
  门禁链会自动把提供者侧从 SKIP 切到实际校验。
- **T-004 / T-006**（runtime / 提示词）：效果类改动会被自动识别为 security +
  提示词相关，需跑黄金集；同时在 `run_golden_set.py` 的 `get_output()` 接模型调用。
- **T-007**（billing）：资金类，自动走全量门禁 + 双人评审。
- 所有工单：领地在工单里声明（`## 文件领地`），门禁链据此核对，越界即 FAIL。