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

## 前置（实测步骤，照抄可跑）

### 契约测试框架（T-010）

```bash
# 1) 建虚拟环境
uv venv tests/contracts/.venv --python 3.13

# 2) 装依赖（全部 pin 版本，见 requirements.txt）
uv pip install --python tests/contracts/.venv/bin/python -r tests/contracts/requirements.txt
```

验证装好了：

```bash
tests/contracts/.venv/bin/python -c "import schemathesis, openapi_spec_validator; print('deps OK')"
```

### 常见踩坑（都是本项目实际踩过的）

| 现象 | 原因 | 解法 |
|---|---|---|
| `ModuleNotFoundError: No module named 'schemathesis'` | 跳过了第2 步，或在别的目录建了 venv | 用 `--python tests/contracts/.venv/bin/python` 显式指定解释器，不要依赖「当前激活的 venv」 |
| `ModuleNotFoundError: No module named 'linkai_xxx'`（跑某个服务的测试时） | 那个服务是 **editable 安装**，不是 `uv sync` | 本仓各服务（如 `services/model-proxy`）用 `uv pip install -e ".[dev]"` 安装，见各自 README。`uv sync` 仅在该服务有 `uv.lock` 时才适用 |
| pytest 进程被 SIGTERM / 静默退出（无任何输出） | **不是代码问题**，是本机内存不足被 OOM killer 杀 | `vm_stat \| head -3` 看 Pages free；关掉部分应用后重跑。CI runner 不受影响 |
| pytest 报 `file or directory not found: tests/contracts` | 在 `tests/contracts/` 目录内用了仓库根相对路径 | 跑仓库根，或用 `--rootdir` 指定 |

> 坑位来源：这些不是设想的风险，是 T-010 交付过程中在本机与team-lead 复跑时
> 实际遇到并记录下来的。**遇到新坑请往这张表里加一行**，别让下一个人重踩。

## 运行

```bash
# 离线消费者侧 + 架构守卫（无需任何服务，CI 必跑）
tests/contracts/.venv/bin/python -m pytest tests/contracts \
  -m "consumer or arch_guard" -q --no-header

# 提供者侧（需要对应服务在 LINKAI_BASE_URL 上跑起来）
LINKAI_BASE_URL=http://127.0.0.1:8000/api/console/v1 \
LINKAI_TEST_TOKEN=<accessToken> LINKAI_TEST_TENANT_ID=<tenantId> \
  tests/contracts/.venv/bin/python -m pytest tests/contracts -m provider -q
```

未设置 `LINKAI_BASE_URL` 时，提供者侧用例自动 `skip`（**不会假装通过**——这是门禁链的
硬要求：未跑 ≠ 通过，报告里会显式标注 SKIP）。

## 目录

```
tests/contracts/
├── requirements.txt            # pin 版本的 Python 依赖
├── conftest.py                 # 契约加载 + LINKAI_BASE_URL 门控 + SKIP 语义
├── test_consumer_sdk_drift.py  # 消费者侧：sdk-ts/sdk-py 生成物是否与契约同步
├── test_consumer_openapi_valid.py  # 消费者侧：OpenAPI 规范自身合法性
├── test_provider_console.py    # 提供者侧：console-api 属性测试
├── test_provider_service.py    # 提供者侧：service-api 属性测试
└── test_arch_guards.py         # 架构守卫：租户头/错误信封/安全声明
```