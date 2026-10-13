"""LinkAI 契约测试框架 —— 公共装置。

设计要点（对应工单 T-010 验收标准）：

1. **契约只读**：本框架绝不写`packages/contracts/**`。铁律 1「契约先行」意味着
   契约是单一事实源，QA 只能发现缺口并上报（工单「契约缺口上报」节），不能自行修补。
2. **SKIP ≠ PASS**：未配置服务 BASE_URL 时，提供者侧用例 skip。门禁链据此把
   「提供者侧」标为 SKIP 而非 PASS——避免假绿灯，这是 T-013 以来团队反复踩的坑。
3. **契约版本可追溯**：每个用例报告里带契约版本号，契约升版时历史报告可对齐。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

# tests/contracts/conftest.py -> tests/contracts -> tests -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "packages" / "contracts"
OPENAPI_DIR = CONTRACTS_DIR / "openapi"
SDK_TS_DIR = REPO_ROOT / "packages" / "sdk-ts"
SDK_PY_DIR = REPO_ROOT / "packages" / "sdk-py"

#: 服务 base_url 环境变量名（各服务工单在 CI 里注入）
BASE_URL_ENV = "LINKAI_BASE_URL"
#: 认证 token 环境变量名。契约里除 login类端点外都要求 bearerAuth +
#: X-Tenant-Id（多租户铁律 6），属性测试必须带上，否则测的是 401 不是契约。
TOKEN_ENV = "LINKAI_TEST_TOKEN"
TENANT_ENV = "LINKAI_TEST_TENANT_ID"

#: 契约文件清单：文件名 -> 消费者侧的 SDK 产物目录
CONTRACT_FILES = {
    "console-api.yaml": SDK_TS_DIR,
    "service-api.yaml": SDK_TS_DIR,
}


def load_spec(name: str) -> dict[str, Any]:
    """加载一份契约（已解 $ref 由schemathesis / spec-validator 负责）。"""
    path = OPENAPI_DIR / name
    if not path.exists():
        pytest.fail(f"契约文件缺失：{path}（契约先行铁律：没有契约就没有可测的东西）")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def contract_version(name: str) -> str:
    return str(load_spec(name).get("info", {}).get("version", "unknown"))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "provider: 提供者侧契约测试（需服务在 BASE_URL 上运行）"
    )
    config.addinivalue_line(
        "markers", "consumer: 消费者侧契约测试（离线，不需服务）"
    )
    config.addinivalue_line(
        "markers", "arch_guard: 架构守卫规则（铁律的可机检部分）"
    )


def pytest_report_header(config: pytest.Config) -> list[str]:
    lines = ["linkai-contract-tests:"]
    for name in CONTRACT_FILES:
        path = OPENAPI_DIR / name
        if path.exists():
            lines.append(f"  {name}@v{contract_version(name)}")
    url = os.environ.get(BASE_URL_ENV)
    lines.append(f"  provider BASE_URL: {url or '<unset → provider 用例将 SKIP>'}")
    return lines


# ── 提供者侧 fixture ──────────────────────────────────────────────────────


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """没有 BASE_URL 时，把 provider 用例显式 skip 并给出可操作的原因。

    刻意不用 `pytest.skip` 在模块导入期调用（那会让整个文件的收集结果变成
    一个笼统的 skip），而是逐条 skip，让报告里能看清「哪些端点本来该测」。
    """
    if os.environ.get(BASE_URL_ENV):
        return
    reason = (
        f"{BASE_URL_ENV} 未设置→ 提供者侧契约测试不可运行。"
        "这不是通过：门禁链会将 provider 项标记为 SKIP 而非 PASS。"
        "本地运行：先起对应服务（docker compose + 各服务 dev 入口），"
        f"再export {BASE_URL_ENV}=http://127.0.0.1:<port>/<base-path>。"
    )
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "provider" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def base_url() -> str:
    url = os.environ.get(BASE_URL_ENV, "").rstrip("/")
    if not url:
        pytest.skip(f"{BASE_URL_ENV} 未设置")
    return url


def build_auth_headers() -> dict[str, str]:
    """属性测试用的公共头。

    契约要求除`x-public` 端点外都带 bearerAuth + X-Tenant-Id。缺任一头，
    测出来的就全是 401/422，属性测试失去意义。

    刻意做成**普通函数**而非 fixture：schemathesis 的 `@schema.parametrize()`
    会把测试函数签名里的每个名字都当作 case 注入源，签名里出现 fixture 名会
    与 schemathesis 的注入机制冲突；而 pytest 9 又禁止直接调用 fixture
    （"Fixture called directly"）。普通函数两头都躲得开。
    """
    headers = {"Content-Type": "application/json"}
    token = os.environ.get(TOKEN_ENV)
    tenant = os.environ.get(TENANT_ENV)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if tenant:
        headers["X-Tenant-Id"] = tenant
    return headers


@pytest.fixture(scope="session")
def auth_headers() -> dict[str, str]:
    return build_auth_headers()


@pytest.fixture(scope="session")
def console_spec() -> dict[str, Any]:
    return load_spec("console-api.yaml")


@pytest.fixture(scope="session")
def service_spec() -> dict[str, Any]:
    return load_spec("service-api.yaml")