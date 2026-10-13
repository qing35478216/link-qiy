# LinkAI QA 契约测试框架

对 `packages/contracts/openapi/` 下的冻结契约做**双侧**一致性校验：

| 侧 | 校验对象 | 工具 | 落地方式 |
|---|---|---|---|
| 提供者侧（Provider） | 服务实现 vs 契约 | [schemathesis](https://github.com/schemathesis/schemathesis) 4.31.0（MIT） | 属性测试打真实 HTTP 服务，校验 status/content-type/response-schema |
| 消费者侧（Consumer） | 生成物 sdk-ts / sdk-py vs 契约 | `pytest` + `openapi-spec-validator` + 自研生成物漂移比对 | 离线，不需要跑服务 |

## 为什么选 schemathesis 而不是 Pact（铁律 8 开源选型）

对比表见 `../../.ai-team/tickets/T-010.md` 的「开源选型对比表」。要点：

- **Pact** 需要先跑起来消费者与提供者各一个进程、维护 pact broker/共享契约文件，且对
  「同一份 OpenAPI 已经是单一事实源」的场景是重复表达。Phase 0 消费者就是本仓库的
  sdk-ts（生成物），不需要独立的消费者服务进程。
- **schemathesis** 直接以 OpenAPI 为唯一事实源生成属性测试，覆盖「实现漂移」
  （响应不符合 schema、未声明状态码、5xx），这正是 Phase 0 最需要守的东西。

Pact 双侧用例在服务落地后（Wave 2 跨服务计费/渠道）再引入，届时另立工单。

## 前置

```bash
# Python 侧（schemathesis 用例）
uv venv tests/contracts/.venv --python 3.13
uv pip install --python tests/contracts/.venv/bin/python -r tests/contracts/requirements.txt
```

`requirements.txt` 全部 pin 版本。

## 运行

```bash
# 离线消费者侧（无需任何服务，CI 必跑）
tests/contracts/.venv/bin/python -m pytest tests/contracts -m "not provider" -q

# 提供者侧（需要对应服务在 BASE_URL 上跑起来）
BASE_URL=http://127.0.0.1:8000/api/console/v1 \
  tests/contracts/.venv/bin/python -m pytest tests/contracts -m provider -q
```

未设置 `BASE_URL` 时，提供者侧用例自动 `skip`（**不会假装通过**——这是门禁链的硬要求：
未跑 ≠ 通过，报告里会显式标注 SKIP）。

## 目录

```
tests/contracts/
├── requirements.txt            # pin 版本的 Python 依赖
├── conftest.py                 # 契约加载 + BASE_URL 门控 + SKIP 语义
├── test_consumer_sdk_drift.py  # 消费者侧：sdk-ts/sdk-py 生成物是否与契约同步
├── test_consumer_openapi_valid.py  # 消费者侧：OpenAPI 规范自身合法性
├── test_provider_console.py    # 提供者侧：console-api 属性测试
├── test_provider_service.py    # 提供者侧：service-api 属性测试
└── test_arch_guards.py         # 架构守卫：租户头/错误信封/安全声明
```