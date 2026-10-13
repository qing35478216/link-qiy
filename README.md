# LinkAI 复刻工程

1:1 复刻 [LinkAI](https://link-ai.tech) 一站式 AI 智能体平台。

> **核心理念：平台做框架，用户做创造。** 平台把"模型、提示词、知识、工具、流程、渠道、分发、变现"八大框架做到可扩展、可治理；智能体、知识、流程和内容由用户自己在框架上创造，生态自生长。

## 快速导航

| 目录 | 内容 |
|------|------|
| `AGENTS.md` | **AI 团队宪法**——所有编码智能体动手前必读（架构铁律 + 工程规范 + 工作协议） |
| `docs/01-功能拆解蓝图.md` | 对标物全貌：控制台实测详录 + 功能拆解 |
| `docs/02-团队组建与开发实施方案.md` | 八大框架设计、团队编制、四阶段开发计划 |
| `docs/03-开发实现框架设计.md` | 架构基线：monorepo、四层架构、契约先行、工作流引擎 |
| `docs/04-模块级实施规格.md` | 模块级实施规格：UI 规范 / 前端 / 后端 / 测试 / 审核人制度 |
| `docs/05-AI开发团队与提示词工程.md` | AI 团队编制与提示词工程（12 角色提示词 + 质量门禁） |
| `linkai-screenshots/` | 视觉与交互基准（25 张实测截图 + 11 份配置全文） |
| `.ai-team/` | AI 团队工作区：角色提示词 / 工单队列 / 模板 |
| `packages/` | contracts（契约单一事实源）、sdk-ts、sdk-py、ui、node-registry |
| `services/` | platform、runtime、model-proxy、knowledge、workflow、billing、gateway |
| `apps/` | web-console、web-marketing、web-studio、embed-sdk、docs |

## 技术选型

| 层 | 选型 |
|---|---|
| 控制台 | Vue3 + Element Plus + Pinia + TanStack Query |
| Studio/画布 | React + React Flow + tldraw |
| 营销站 | Next.js 14 + Tailwind（SSG） |
| 嵌入 SDK | 原生 JS + iframe Shadow DOM |
| 后端 | Python（FastAPI 四层架构）+ Go（网关）微服务混合 |
| 工作流引擎 | 自研 DAG 执行器（节点注册制） |
| RAG | pgvector + BM25 + 自研管道 |
| 数据 | PostgreSQL / Redis / MinIO / ClickHouse / MQ |
| 基础设施 | Docker + K8s + Prometheus/Grafana/Loki + OTel |

## 开发模式：Orchestrator + Specialists

```
人类（架构决策 + 验收：契约评审 / 架构变更 / 黄金集 / 资金 / 里程碑）
  └── Orchestrator（拆工单 → 派发 → 门禁收口 → 升级，不写代码）
        ├── Contract Engineer（契约唯一守门人，最高优先级）
        ├── 后端线：Platform / Runtime / AI Framework / Workflow / Billing
        ├── 网关线：Channel Engineer（Go）
        ├── 前端线：Console / Canvas / Marketing & SDK
        └── QA & Reviewer（门禁链 + 架构守卫）
```

WorkBuddy 专家中心已注册团队专家 **linkai-dev-team**，对话即可调度整个团队。

## 当前进度

**Phase 0（框架地基）**——工单队列 `.ai-team/tickets/`（T-000 ~ T-012），状态 PENDING。
出口标准：能登录 → 建轻量应用 → 配模型和提示词 → 对话 → 被配额和积分约束。

## 本地开发

```bash
# 起本地依赖（PG/Redis/MinIO）
docker compose up -d

# 领一个工单开工
git worktree add ../wt-T-xxx -b feat/T-xxx-简述
```

（脚手架细节见工单 T-000，完成后本节补充确切命令。）
