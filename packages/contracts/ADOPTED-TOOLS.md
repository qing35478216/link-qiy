# ADOPTED-TOOLS —— 开源选型记录（铁律 8）

## SDK 生成（scripts/generate.mjs）

| 候选 | 维护活跃度 | Issue 响应 | 许可证 | 技术栈匹配 | 结论 |
|---|---|---|---|---|---|
| **orval** | 活跃（近 3 月多次发版） | 良好 | MIT | TS 原生；**原生生成 MSW handlers**（工单硬性要求） | ✅ **sdk-ts 选定** |
| openapi-typescript + openapi-fetch | 活跃 | 良好 | MIT | 仅类型+轻客户端，MSW 需另配 msw-auto-mock | 备选 |
| openapi-generator-cli | 活跃 | 中等 | Apache-2.0 | 依赖 Java，产物风格笨重 | 弃（体积/依赖重） |
| **openapi-python-client** | 活跃 | 良好 | MIT | 现代 Python（httpx + pydantic v2），与 FastAPI 栈天然匹配 | ✅ **sdk-py 选定** |
| datamodel-code-generator | 活跃 | 良好 | MIT | 泛用模型生成，无 API 客户端 | 备选 |

理由：工单要求 sdk-ts 带 MSW handlers（前端 Mock 驱动开发）——orval 原生支持；sdk-py 要求 Pydantic + FastAPI 路由桩——openapi-python-client 生成的 httpx 客户端与 pydantic v2 模型直接可用。两者均 MIT、维护活跃、零重型依赖。

> 实际产物说明（v0.1.1 勘误）：orval 当前配置生成 axios 客户端 + 类型 + MSW handlers，**不含 TanStack Query hooks**（早期本文档误报）。若 T-011 之后需要 query hooks，另立工单在 orval.config.ts 增配 query client 生成。

## 契约治理工具（既有，T-000 前由契约工程师建立）

- @stoplight/spectral-cli（MIT）—— lint 机检；自定义规则集见 .spectral.yaml
- oasdiff（MIT）—— breaking change 检测（scripts/diff.sh）

## 变更记录

- 2026-10-13：sdk-ts 选 orval、sdk-py 选 openapi-python-client（主理人代管 T-001 期间定稿，何约复核）
