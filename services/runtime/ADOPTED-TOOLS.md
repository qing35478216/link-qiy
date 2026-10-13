# services/runtime 开源选型记录（AGENTS.md 铁律 8 必填）

检索渠道：WebSearch/WebFetch（2026-10-13）。核查四项：维护活跃度 / Issue 响应 /
许可证 / 技术栈匹配。新依赖全部进本文件 + pyproject 版本 pin + lockfile。

## 1. HTTP 客户端：httpx（采用）

| 候选 | 许可证 | 维护活跃度 | 结论 |
|---|---|---|---|
| **httpx 0.28.x** | BSD-3-Clause | encode 组织，2026 年仍有提交与发版；PyPI 周下载量级千万 | **采用**：async 原生 + respx mock 生态 + model-proxy 同款（跨服务一致） |
| aiohttp | Apache-2.0 | 活跃 | 不选：respx 生态不覆盖；与 model-proxy 技术栈分裂 |
| requests | Apache-2.0 | 活跃 | 不选：同步，热路径（流式）不合适 |

集成方式：`infra/model_proxy_client.py` 与 `infra/app_profile_provider.py`
共用 `httpx.AsyncClient`（连接复用；首 token 优化的基础）。测试用 respx mock 回放，
禁真实出网（conftest socket 级兜底，同 model-proxy）。
注意（已记录）：Gentoo 打包信息显示上游已不接受公开 bug report（discussions/3784），
 Issue 转讨论区；不影响使用，选型时知悉。

## 2. Token 估算：启发式自研（采用）；tiktoken 列为后续优化

| 候选 | 许可证 | 覆盖 | 结论 |
|---|---|---|---|
| tiktoken | MIT | 仅 OpenAI 系词表 | Phase 0 不采用：runtime 经 model-proxy 路由多厂商（deepseek/qwen/glm/anthropic…），单分词器覆盖不了；按模型切换分词器=把厂商知识搬进 runtime |
| HuggingFace tokenizers / SentencePiece | Apache-2.0 / Apache-2.0 | 按模型族分裂 | 同上，且引入重依赖 |
| **启发式估算（自研 ~40 行）** | — | 厂商无关 | **采用**：CJK≈1 token/字、其余≈1 token/4 字符；与 model-proxy 既有 HeuristicTokenEstimator 同口径；仅用于上下文预算截断（装配决策），计费用量以真实 usage 为准 |

自研理由（铁律 8 要求）：现有库均按模型族分裂，而 runtime 的核心诉求是
"厂商无关的确定性预算截断"，无单一库满足；实现 40 行内、零依赖、可单测。
后续优化：按 model_code 分派 tiktoken 精确化（不改变装配函数签名）。

## 3. ORM / 迁移：SQLAlchemy 2.0 + Alembic（采用）

| 候选 | 许可证 | 结论 |
|---|---|---|
| SQLAlchemy 2.0 | MIT | **采用**：platform 同款（同库不同表，迁移体系一致）；ORM 只在 infra 层 |
| Tortoise ORM | Apache-2.0 | 不选：与 platform 技术栈分裂 |
| Alembic | MIT | **采用**：platform 同款迁移工具；`alembic/versions/0001` 建 runtime 四表 |

## 4. 测试：pytest + pytest-asyncio + respx（采用）

| 候选 | 许可证 | 结论 |
|---|---|---|
| pytest 8 + pytest-asyncio（asyncio_mode=auto） | MIT | **采用**：model-proxy 同款配置 |
| respx | MIT | **采用**：httpx mock，回放 model-proxy/platform 响应不触网 |
| unittest.IsolatedAsyncioTestCase | — | 不选：生态与夹具弱于 pytest |

## 5. SSE 帧封装：自研（~5 行，无库）

Runtime Event 协议是平台自有契约（runtime-events.yaml），无通用库可对标；
FastAPI `StreamingResponse` 原生支持 async generator，帧封装为
`data: {json}\n\n`（`api/routers/chat.py::_sse_frame`）。自研理由：契约驱动，
引入库只会多一层与协议漂移的风险。

## 6. 结构化日志：structlog（采用）

MIT（实际 dual MIT/Apache-2.0）。platform/model-proxy 同款实现
（`infra/logging.py` 与 platform 逐行一致，保证采集侧统一解析）。
