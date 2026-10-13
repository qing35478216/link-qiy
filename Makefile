# LinkAI Phase 0 工程化入口
#
# 常用：
#   make dev     起本地依赖（PG/Redis/MinIO）
#   make gate    门禁链：目前真实步骤 = contracts lint，其余为占位 TODO [T-xxx]
#   make test    测试入口（占位，待服务代码落地）
#   make clean   停依赖并清数据卷（危险：删本地数据）
#
# 分支约定：feat/T-xxx-简述，短命分支，禁止直推 main（AGENTS.md 工作协议）

COMPOSE := docker compose

.PHONY: dev deps-up gate test clean lint-contracts

## 起本地开发依赖（PG16+pgvector / Redis7 / MinIO）
dev: deps-up
deps-up:
	$(COMPOSE) up -d --wait

## 门禁链：一个命令跑完所有质量检查
# 真实步骤（Phase 0 已可用）：
#   1. contracts lint（spectral 契约机检）
# 占位步骤（服务代码落地后由对应工单启用，届时删除 TODO 注释并替换为真实命令）：
#   - gateway (Go)        TODO [T-002]：cd services/gateway && golangci-lint run
#   - platform (Python)   TODO [T-003]：cd services/platform && uv run ruff check . && uv run mypy --strict src && uv run pytest
#   - runtime (Python)    TODO [T-004]：同上
#   - workflow (Python)   TODO [T-005]：同上
#   - knowledge (Python)  TODO [T-006]：同上
#   - model-proxy (Python) TODO [T-007]：同上
#   - billing (Python)    TODO [T-008]：同上
#   - 前端 eslint+prettier TODO [T-0xx]：pnpm -r lint（web-console / web-marketing / web-studio）
gate: lint-contracts
	@echo "== gate: contracts lint passed =="
	@echo "== gate: 服务级检查均为占位 TODO，待各服务工单落地后启用 =="

lint-contracts:
	npm --prefix packages/contracts run lint

## 测试入口（领域层单测 ≥70% 覆盖率为验收线，服务落地后填充）
test:
	@echo "TODO [T-003~T-008]: 各服务 pytest 入口就绪后在此聚合"

## 停依赖并删除数据卷（会丢本地数据，谨慎）
clean:
	$(COMPOSE) down -v
