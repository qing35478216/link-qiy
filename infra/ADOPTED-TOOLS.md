# ADOPTED-TOOLS — T-000 开源选型记录（铁律 8）

记录日期：2026-10-13。核查项：①维护活跃度 ②Issue 响应 ③许可证兼容（SaaS 场景）④技术栈匹配。
全部为 MIT/Apache-2.0/BSD 类宽松许可证，可直接引入，无 AGPL/GPL 传染风险。

## Monorepo / 包管理

| 选型 | 候选对比 | 结论与理由 |
|---|---|---|
| **pnpm workspace**（Node ≥20） | npm workspaces（无 lockfile 去重优势）、Yarn 4（P'n'P 兼容坑）、Bun（太新，CI 生态不稳） | pnpm 内容寻址 store + 严格 node_modules，monorepo 省盘且防幽灵依赖；docs/03 2.1/第六部分已定为 pnpm；Apache-2.0，活跃 |
| **uv**（Python） | Poetry（solver 慢、PEP 621 历史包袱）、pip+venv（无 lock）、PDM | uv（Astral，Rust）速度数量级领先且原生 workspace/lockfile，Apache-2.0；docs/03 已定 uv |
| Go modules | — | 官方工具链，无争议 |

## 本地依赖栈（docker-compose）

| 组件 | 选型 | 候选对比 | 结论与理由 |
|---|---|---|---|
| PostgreSQL + 向量 | **pgvector/pgvector:pg16** | postgis/pgvector（多带 PostGIS，用不上）、自建 init 装 extension | pgvector 官方镜像一键 PG16+vector，Phase 0 单容器搞定向量+主库（Dify 同款演进路径，先 PG 后 Milvus/Qdrant 待数据量评估）；PostgreSQL License |
| 缓存/MQ | **redis:7-alpine** | Redis 8（2025 起双许可证 RSALv2/SSPLv1，非 OSI）、KeyDB/Valkey | **Redis 7 是最后一个 BSD 大版本**——Redis Ltd. 8 起许可证变更，SaaS 合规角度锁 7；后续关注 Valkey（BSD，Linux 基金会）演进 |
| 对象存储 | **minio/minio** | 云服务 S3（本地开发不可控）、SeaweedFS | MinIO 事实标准本地 S3，console 自带；注意 MinIO 2025 起转向 AGPLv3 为主（社区版），**私有化交付时需法务确认或评估替代（SeaweedFS/云 S3），已列为风险登记**；本地开发场景无分发行为，风险可控 |

## CI / 质量工具

| 选型 | 候选对比 | 结论与理由 |
|---|---|---|
| **GitHub Actions** | GitLab CI（托管成本）、Jenkins（运维负担） | 仓库在 GitHub，原生集成零额外基建；docs/03 已定 |
| **Ruff**（Python lint+format） | flake8+isort+black 三件套（慢、配置碎） | Ruff（Astral）单工具替代组合，快 10-100x，MIT，规则覆盖 docs/03 规范 |
| **mypy --strict** | pyright（IDE 强但 CI 集成略重） | 规范已定为 mypy strict，保持 |
| **Spectral**（OpenAPI lint） | vacuum、openapi-generator 自带校验 | contracts 包已采用（@stoplight/spectral-cli），T-001 继续沿用 |
| **Trivy**（依赖/镜像扫描） | Grype（好但 Actions 集成弱）、Snyk（商用配额） | Trivy Apache-2.0 + 官方 Actions，docs/03 第六部分已定 |
| 服务脚手架 | **纯模板目录 + 30 行 shell** | cookiecutter（成熟但多一个 Python 工具依赖与模板语法学习成本） | 模板仅 4 个文件，占位符替换用 sed 即可，零依赖进 gate；若模板膨胀到含条件分支再迁 cookiecutter |

## 后续工单选型时需沿用本表格式补录

向量库正式选型（Milvus/Qdrant/pgvector 对比表）、工作流引擎内核、插件 gRPC 框架、前端画布（React Flow/tldraw）等——在对应工单 PR 中补对比表，并回写本文件。
