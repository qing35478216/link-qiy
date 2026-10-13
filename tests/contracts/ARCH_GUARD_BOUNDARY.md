# 架构守卫与 spectral 的分工边界

> 决策依据：主理人 T-010 评审裁决——「重复不叫纵深，叫维护负担」。
> 契约改动需两处同改，漏改概率远高于「有人显式跳过 spectral」：
> 前者是静默腐化，后者是显式行为。本项目已吃过 3 次静默死亡的亏。

## 划界原则

**spectral 管「单个操作写得对不对」，pytest 管「多个操作之间一致不一致」。**

这条线不是随手划的，它对应两类判定范式：

|范式 | spectral 能做| pytest 能做 |
|---|---|---|
| 逐点判定 | ✓ 对每份规范、每个操作独立下判断 | 能，但会重复表达 |
| 跨点比对 | ✗ JSONPath 看不到别的文件/别的操作 | ✓ 取基准、比对差异 |
| 跨文件 $ref 解析 | 部分（能解析，不看被引用文件内容） | ✓ 直接读 `../schemas/*.yaml` |
| 元数据自检 | ✗ | ✓（如 known_gaps 基线完整性） |

## 当前分工

### spectral 负责（`.spectral.yaml` 的 linkai-* 规则）
`operationId` 存在性/唯一性/命名、路径 kebab-case、summary/tags 必填、
4xx/5xx 响应声明、安全声明显式化、错误信封形状、schema description、
deprecated 必须带 x-sunset。

### pytest 负责（`tests/contracts/test_arch_guards.py` + 其余三个文件）

| 用例 | 留在 pytest 的具体原因 |
|---|---|
| `test_console_operations_declare_tenant_context` | 租户头通过 `$ref: ../schemas/common.yaml#/TenantHeader` 声明。spectral 的 JSONPath 只能看到 `$ref` 这个字符串，看不到被引用文件里的 `name: X-Tenant-Id`。**这不是能力问题而是设计问题**：让它表达就得让 JSONPath 钻到 schemas/，那是契约结构本身的不合理（公共片段用 $ref 正是为了单一事实源）。 |
| `test_service_api_keys_bind_tenant` | 判定依据是「用户面租户由 Key 归属解析」这条**跨规范语义约定**，需要对比 console-api 与 service-api 两份规范的 security 方案。spectral 是单文件 lint，表达不了跨文件约定。 |
| `test_public_operations_are_actually_public` | `x-public: true` 与 `security: []` 的**矛盾检测**（两个字段都写了但语义打架）。spectral 逐规则独立判断，做不了「A 与 B 应当一致」。 |
| `test_login_paths_agreement_consistency` | 同上，是**跨端点一致性**：取协议约束最严的登录通道作基准，比对其他通道。与 spectral 的逐操作判断是不同范式。 |
| `test_error_envelope_referenced_by_operations` | 检测 `$ref` **有没有被用上**。spectral 只校验 `$ref` 写得对不对，不校验它指向的东西是否真的被引用——契约里定义了 Error 却无人引用，spectral 完全无感（GAP-CONTRACT-002 就是这么漏掉的）。 |
| `test_contracts/test_consumer_*` | 规范合法性、SDK 生成物双向漂移——spectral 完全不覆盖（它不读生成物）。 |
| `test_known_gaps_baseline_has_provenance` | 检查 `known_gaps.py` 自身元数据完整性，与契约内容无关。 |

## 迁出记录（防止再次重复实现）

- **2026-10-13** `test_operation_ids_are_unique` → 移除。
  `.spectral.yaml` 的 `operation-operationId-unique: error` 已覆盖，
  且 `spectral:oas` 规则集自带该检查。我们再写一遍纯属重复维护。

## 建议迁回 spectral 的清单（待主理人裁定）

以下 4 条 spectral **能等价表达**，迁回可消除双维护。**裁定前保持现状**——
CI 当前依赖这些用例在跑，贸然移除会让防线出现空窗。

| # | pytest 用例 | 对应 spectral 规则 | 现有严重级 | 迁回后的风险 |
|---|---|---|---|---|
| 1 | `test_every_operation_declares_security` | `linkai-security-defined` | error | 无。语义完全一致 |
| 2 | `test_operations_have_summary` | `linkai-operation-summary-required` | warn | 无。pytest 版额外接受 `description` 作为替代，spectral 版只查 summary——**迁移时需把 pytest 的宽松口径同步给 spectral**，否则会新增误报 |
| 3 | `test_error_envelope_schema_is_wellformed` | `linkai-error-envelope-shape` | error | **有差异**：spectral 检查每个错误响应的 schema；pytest 检查 `common.yaml#Error` 这一个定义。两者对象不同，不是同一条规则，建议**两者都留** |
| 4 | `test_write_operations_declare_error_responses` | `linkai-error-response-4xx` | warn | **有差异**：spectral 对所有含 requestBody/parameters 的操作生效；pytest 只对写操作（POST/PUT/PATCH）生效，且 pytest 走缺口基线。spectral 侧已被甲方降为 warn 且**无法表达缺口基线**，故建议**保留 pytest 版** |

**结论**：真正能干净迁回的只有 #1。#2 需同步口径，#3 #4 存在语义差异或缺口基线能力缺失，建议留在 pytest。

## 三份架构守卫的技术债（记入 T-015，不在T-010 内动）

| 位置 | 守卫对象 | 归属 |
|---|---|---|
| `tests/contracts/test_arch_guards.py` | **契约层**规则 | 本工单 |
| `services/platform/tests/architecture/test_layering.py` | platform 代码分层 | T-002 |
| `services/model-proxy/tests/unit/test_architecture_guard.py` | model-proxy 代码分层 | T-005 |

后两者是**同一种规则（代码分层）在两个服务里各写一遍**——真正的重复维护风险：
每加一个服务就要抄一份，改规则要改 N 处。

建议 T-015 抽出共享守卫（如 `tests/arch/shared_layering_guard.py`），
各服务只提供自己的路径与例外清单。**本工单不动**，仅登记。