# services/model-proxy 开源选型记录（铁律 8）

> 通用模块动手前先检索 GitHub 成熟库；核查四项：① 近3 个月有提交/发版 ② Issue 响应
> ③ 许可证兼容（MIT/Apache-2.0/BSD 可直接引入）④ 技术栈与依赖版本匹配。
> 本文件记录 T-005 引入的第三方库选型对比与理由。数据检索时间 **2026-10-13**。

## 0. 结论先行：为什么**不**直接用现成 LLM 网关

Phase 0 最大的诱惑是"直接装 LiteLLM"——它是这个赛道事实上的开源标准。
核查后**不采用**，理由是它与我们最核心的两条铁律正面冲突：

| 冲突点 | 我们的硬要求 | LiteLLM 的现实 |
|---|---|---|
| **铁律 4 注册机制** | 新厂商 = 写适配器 + 注册表，**内核零改动**；内核可被AST 守卫测试保护 | `litellm/main.py` 内含 100+ 厂商的if/elif 分派。**新接厂商必须改上游内核**（或改上游的 provider map），我们无法在不改 vendor 代码的前提下满足铁律 4，也无法写守卫测试证明"没改内核" |
| **契约唯一事实源** | 请求/响应形态由 `packages/contracts/**` 冻结（铁律 1） | LiteLLM 自带 `model_prices_and_context_window.json`（各家价格/上下文/能力）作为第二事实源，与我们的 `ModelCard`目录重复且会漂移 |

其余因素（详见 §1）：许可证状态不干净、体积巨大、与我们的降级链/计量语义不匹配。

**我们实际引入的只有一个出网库（httpx，BSD-3-Clause）**，其余全部自研——
自研范围是"网关编排 + 适配器协议 + 计量"，而非"HTTP 客户端"或"通用能力"。

---

## 1. 网关内核候选对比

| 候选 | 维护活跃度 | Issue 响应 | 许可证 | 技术栈匹配 | 结论 |
|---|---|---|---|---|---|
| **LiteLLM**（BerriAI/litellm） | 极活跃（2026-10-13 当日仍有提交，61k stars） | 差：**5505 open issues**，积压严重 | **NOASSERTION**（GitHub 未能识别）。实为：仓库根 MIT，但 `enterprise/` 目录另有商业许可（见下方实测） | Python 匹配；但**内核含厂商硬分支**，与铁律 4 冲突 | **不采用**（铁律 4 + 许可不干净 + 双事实源） |
| **Portkey Gateway**（portkey-ai/gateway） | 停滞（最后提交 2026-05-25，距检索 4.5 个月） | 296 open | MIT | **TypeScript/Node 栈**，我们是 Python 服务 | 不采用（栈不匹配 + 活跃度不达标） |
| **Helicone**（Helicone/helicone） | 活跃（2026-10-10） | 168 open | Apache-2.0 | 定位是**可观测性**（网关是附属能力），非编排内核 | 不采用（定位错配：我们要的是网关不是观测） |
| any-llm（mozilla-ai/any-llm） | 活跃（2026-10-13） | — | Apache-2.0 | Mozilla 出品，LLM 抽象层，规模远小于 LiteLLM | 备选（若将来需要扩展能力抽象可再评） |

**LiteLLM 许可证实测**（`GET /repos/BerriAI/litellm/license` 首段原文）：

> Portions of this software are licensed as follows:
> * All content that resides under the "enterprise/" directory ... is licensed under the license defined in "enterprise/LICENSE".
> * Content outside of the above mentioned directories ... is available under the MIT license

即：核心 MIT，但 `enterprise/` 是独立商业许可，GitHub 因此报`NOASSERTION`。
按 AGENTS.md 铁律 8③，GPL/AGPL 必须升级人类确认；`NOASSERTION` 属同类风险，
**若未来评估引入需人类拍板**。这是"不采用"的理由之一，但**不是主因**——
主因是铁律 4 的架构冲突（那个是死结，许可证是可谈的）。

**自研理由（写入工单）**：现有库无法同时满足"内核零改动的厂商扩展"与"契约唯一事实源"
两条铁律；且我们需要的编排内核（约 500 行领域代码）远小于引入 100+ 传递依赖的代价。
满足 AGENTS.md"仅当现有库无法满足需求时才允许自研"的条件。

---

## 2. 厂商 SDK：统一走 OpenAI 兼容 HTTP，**不引入任何厂商 SDK**

这是本工单**最重要的选型决策**。逐家核查结果：

| 厂商 | 官方 SDK | 许可证 | 活跃度 | OpenAI 兼容端点 | 结论 |
|---|---|---|---|---|---|
| OpenAI | `openai/openai-python` | Apache-2.0 | 活跃（2026-10-13） | ✅ 原生 | **不引入**，走兼容 HTTP |
| Anthropic | `anthropics/anthropic-sdk-python` | **MIT** | 活跃（2026-10-09） | ❌ **不兼容**（需协议翻译） | **不引入**，自写约 120 行 Messages 翻译 |
| 阿里通义 | `dashscope/dashscope-sdk-python` | 未在GitHub 明确标注 | 活跃 | ✅ `compatible-mode/v1` | **不引入** |
| 智谱 GLM | `MetaGLM/zhipuai-sdk-python-v4` | MIT | **停滞**（最后提交 2025-10-21，198 stars） | ✅ `open.bigmodel.cn/api/paas/v4` | **不引入** |
| DeepSeek | 无官方 Python SDK | — | — | ✅ 原生兼容 | **不引入** |

**不引入的四个理由**（按重要性）：

1. **许可证与合规风险（铁律 8③）**：厂商 SDK 的许可状态参差——`dashscope` 仓库未清晰标注
   主许可（这类商业厂商 SDK 历史上出现过非商用条款变更），智谱 SDK 虽为 MIT 但已停滞一年
   无人维护。**逐个引入会把这些不确定性引入我们的 SaaS 服务**。统一走公开 HTTP API
   规避了全部 SDK 许可问题（HTTP API 的使用受服务条款约束，不涉及代码许可传染）。
2. **依赖体积与供应链面**：5 家 SDK 会带来数十个传递依赖（含 `requests`/`oss2`/
   `pydantic` 特定版本约束等），与 pnpm "最短发布龄"策略同理，供应链面越小越好。
3. **维护成本**：专有 SDK 各自升级、响应形态各异，每家都要单独写解析与回归。
   OpenAI 兼容接口是**最小公倍数**：5 家里 4 家只差 `base_url`，共用一个基类。
4. **可测试性**：统一形态让回放用例共用同一套断言（本工单 5 家适配器用例仅 ~150 行）。

**必要适配**：Anthropic 单独实现 `AnthropicAdapter`，做 6 处协议翻译
（端点 `/messages`、`x-api-key` 头、system 提为顶层字段、`max_tokens` 必填、
响应 `content[]` 块数组、用量 `input_tokens`/`output_tokens`）。
这些差异**全部封在适配器内**，内核与上层零感知。

**`/healthz/providers` 会输出每家的 `protocol` 字段**（`openai-compatible` / `native`），
新增厂商时该字段自动反映真实协议——避免"文档写错了没人知道"。

### 未来若需厂商专有能力

若将来要用 Assistants API（OpenAI）、Files API、Batch API 等**OpenAI 兼容面覆盖不到**的能力，
应**单独立项**引入对应 SDK，并在工单重新做四项核查 + 人类确认许可证。
本工单不预留这些依赖。

---

## 3. 实际引入的依赖（唯一新增库：httpx）

| 库 | 版本约束 | 许可证 | 引入理由 |
|---|---|---|---|
| **httpx** | `>=0.27` | BSD-3-Clause | 唯一出网客户端。选它而非 `requests`/`aiohttp`：① 原生 async（流式 SSE 是硬需求）② `follow_redirects=False` 可显式表达"禁止重定向"这一安全约束 ③ API 简洁便于在测试中用 respx 回放。**强制只经 `infra/http_client.py` 使用**，架构守卫测试禁止其他文件 import httpx |

其余为脚手架基线（fastapi / uvicorn / opentelemetry-* / structlog，见 pyproject）。
**未引入**：SQLAlchemy / Alembic / Redis 客户端——Phase 0 端口实现全部是内存版
（`infra/memory.py`），接口按 domain `Protocol` 编程，Phase 1 换实现不改业务代码。

## 4. 计量（MeteringEvent）为何自研

现成方案（Langfuse / OpenLLMetry / LiteLLM spend-tracking）都是**观测/成本分析**导向：
记录"这次调用花了多少钱"用于看板，而我们需要的是**跨服务计费事件**（T-007 积分钱包要
原子扣减、要按租户对账、要幂等）。二者语义不同：

- 我们的 `MeteringEvent` 必带 `tenant_id`（铁律 6）与幂等 `event_id`，失败尝试也发
  （`outcome=FAILED`，`credits=0`）但仍留痕以对账；
- 观测类工具的计费模型没有租户隔离概念，也不保证投递语义。

因此自研（约 200 行，含契约字段测试）。**未引入 langfuse**——docs/observability.md
约定的可观测栈是 OTel + 自建 trace，不含 Langfuse。

## 5. SSRF 防护为何自研

`ssrf-proxy` 是本项目**已有的安全边界组件**（T-008 负责 Go 实现），
Python 侧需要的是"调用前校验 + 阻断内网"的闸门逻辑（约 150 行）。
未引入 `ssrf-requests` / `safeurl-python` 等第三方库，理由：

- 它们的判定逻辑（协议白名单、私有网段表、元数据端点表）与我们 T-008 Go 侧的实现
  必须**保持一致**，两套规则漂移会造成"Go 放行 / Python 阻断"或反之的诡异 bug；
- 判定逻辑本身就是几十行常量表，引入依赖的收益低于维护两套规则一致性的成本。

生产环境的出网应经 `ssrf-proxy` 服务（T-008），本模块的本地校验是**第二道防线**
（纵深防御）：即使 ssrf-proxy 未部署或被绕过，闸门仍会拦下内网地址。

## 依赖清单（对应 pyproject，版本由 uv.lock pin）

| 库 | 版本约束 | 许可证 | 引入理由 |
|---|---|---|---|
| httpx | >=0.27 | BSD-3-Clause | 出网 HTTP + SSE（见 §3） |
| fastapi / uvicorn[standard] / opentelemetry-* | 脚手架基线 | — | 模板自带 |
| structlog | >=24.1 | MIT/Apache-2.0 | 结构化日志（observability.md 约定） |
| pytest / pytest-cov / pytest-asyncio / ruff / mypy / black | dev | — | 测试与门禁 |
| **respx** | >=0.22 | BSD-3-Clause | dev 依赖：httpx 回放 mock。**所有厂商用例零触网**（conftest autouse 护栏在 socket 层兜底） |

> 全部为 MIT/BSD/Apache-2.0，**无 GPL/AGPL/非商用许可**，无商业条款风险。
