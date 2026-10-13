"""消费者侧契约测试：生成物（sdk-ts / sdk-py）是否与冻结契约同步。

对应角色定义「契约遵守检查：实现与 OpenAPI 是否一致（生成物 diff 为空才对）」。

三类检查：
1. **端点覆盖**：契约里每个 operationId 都必须在 sdk-ts 里有对应方法——
   漏生成意味着前端根本调不到该端点，且不会报错（最难发现的一类漂移）。
2. **操作集合一致**：sdk-ts 里有、契约里没有的方法 = 契约被改过但没重新生成
   （前端在调一个已不存在的端点）。
3. **Python SDK 同步**：sdk-py 的 api/ 目录按 tag 分组，应与契约 tag 对齐。

这些检查全部离线，只读契约与生成物，不写任何东西。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from conftest import CONTRACT_FILES, SDK_PY_DIR, SDK_TS_DIR

pytestmark = pytest.mark.consumer

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def operations(spec: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """抽取 {operationId: (path, method)}。"""
    out: dict[str, tuple[str, str]] = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict) and op.get("operationId"):
                out[op["operationId"]] = (path, method)
    return out


def spec_path(name: str) -> Path:
    from conftest import OPENAPI_DIR

    return OPENAPI_DIR / name


@pytest.mark.parametrize("contract", sorted(CONTRACT_FILES))
def test_contract_operation_ids_present(contract: str) -> None:
    """契约必须每个操作都有 operationId（生成 SDK 方法名的前提）。"""
    import yaml

    spec = yaml.safe_load(spec_path(contract).read_text(encoding="utf-8"))
    missing = []
    for path, item in (spec.get("paths") or {}).items():
        for method in _HTTP_METHODS:
            op = item.get(method) if isinstance(item, dict) else None
            if isinstance(op, dict) and not op.get("operationId"):
                missing.append(f"{method.upper()} {path}")
    assert not missing, (
        f"{contract} 存在无 operationId 的操作：{missing}。"
        "契约先行铁律：无 operationId 则生成的 SDK 方法名不可控，请由 Contract Engineer 补齐。"
    )


@pytest.mark.parametrize("contract", sorted(CONTRACT_FILES))
def test_sdk_ts_covers_every_operation(contract: str) -> None:
    """sdk-ts 必须覆盖契约里的每个 operationId。

    orval 按 operationId 生成方法名，所以方法名缺失 == 端点没生成。
    """
    import yaml

    spec = yaml.safe_load(spec_path(contract).read_text(encoding="utf-8"))
    ops = operations(spec)
    assert ops, f"{contract} 未解析出任何 operation，契约可能格式异常"

    clients = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((SDK_TS_DIR / "src").glob("*.ts"))
        if not p.name.endswith(".msw.ts")
    )
    assert clients, f"未找到 sdk-ts 客户端产物：{SDK_TS_DIR / 'src'}"

    missing = [op_id for op_id in ops if op_id not in clients]
    assert not missing, (
        f"契约中的 {len(missing)} 个 operationId 未出现在 sdk-ts：{missing}。"
        "生成物与契约漂移——请跑 `pnpm -C packages/contracts generate` 后一并提交 sdk-ts/sdk-py。"
    )


@pytest.mark.parametrize("contract", sorted(CONTRACT_FILES))
def test_sdk_ts_has_no_orphan_methods(contract: str) -> None:
    """反向检查：sdk-ts 不得有契约里已不存在的端点。

    典型触发场景：改了契约却没重新生成，前端还在调已删除的端点。
    """
    import yaml

    spec = yaml.safe_load(spec_path(contract).read_text(encoding="utf-8"))
    ops = operations(spec)

    client_file = SDK_TS_DIR / "src" / (
        "console.ts" if contract.startswith("console") else "service.ts"
    )
    assert client_file.exists(), f"缺少客户端产物：{client_file}"

    text = client_file.read_text(encoding="utf-8")

    # orval v8 的产物结构：`export const getXxxAPI = (axiosInstance) => { ... }`，
    # 每个端点方法在工厂体内以 `const <operationId> = (` 声明（不是 export）。
    # 所以要在工厂体范围内匹配，并剔除两类非端点符号：
    #   - 工厂函数本身（getLinkAIConsoleAPI / getLinkAIServiceAPIOpenAI）
    #   - 每个端点配套的 URL helper（orval 自动生成的 getXxxUrl）
    factory = re.search(
        r"export const (get\w+)\s*=\s*\(\s*axiosInstance[^)]*\)\s*=>\s*\{",
        text,
    )
    assert factory, f"未在 {client_file} 中识别到 orval 客户端工厂函数，产物结构可能已变"
    body = text[factory.end():]

    ops = operations(spec)
    found = set(re.findall(r"\nconst ([A-Za-z0-9_]+)\s*=\s*\(", body))
    orphans = sorted(
        name
        for name in found
        if name not in ops
        # orval 的 URL helper：get<OperationId>Url
        and not re.fullmatch(r"get[A-Z]\w*Url", name)
    )
    assert not orphans, (
        f"sdk-ts 出现契约中不存在的导出方法：{orphans}。"
        "契约已变但生成物未同步，请跑 generate 后提交；"
        "若确为有意删除端点，需同时核对 sdk-py 与前端调用点。"
    )


def test_sdk_py_tag_structure_matches_contract() -> None:
    """sdk-py 按契约 tag 分目录，tag 应与 console-api 对齐。

    契约新增一个 tag（如 Channels）却没重新生成 sdk-py 时，
    该 tag 的端点会被 openapi-python-client 静默丢弃——必须在 QA 层拦住。
    """
    import yaml

    spec = yaml.safe_load(spec_path("console-api.yaml").read_text(encoding="utf-8"))
    contract_tags = {
        tag
        for item in (spec.get("paths") or {}).values()
        if isinstance(item, dict)
        for op in item.values()
        if isinstance(op, dict) and op.get("tags")
        for tag in op["tags"]
    }
    api_dir = SDK_PY_DIR / "src" / "link_ai_console" / "api"
    assert api_dir.exists(), f"缺少 sdk-py api 目录：{api_dir}"
    sdk_tags = {p.name for p in api_dir.iterdir() if p.is_dir() and not p.name.startswith("_")}

    missing = sorted(t.lower() for t in contract_tags if t.lower() not in sdk_tags)
    assert not missing, (
        f"契约 tag 在 sdk-py 中缺失：{missing}（契约 tags: {sorted(contract_tags)}，"
        f"sdk-py dirs: {sorted(sdk_tags)}）。"
        "openapi-python-client 会静默丢弃 tag 下无有效端点的分组，"
        "所以这里必须显式断言，不能靠生成器报错。"
    )


def test_generated_artifacts_are_tracked() -> None:
    """生成物必须落盘在仓库里（漂移比对的前提）。

    若有人把sdk-ts/src 加进 .gitignore，漂移检查会永远「通过」——
    那是假绿灯，必须显式失败。
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "packages/sdk-ts/src"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert len(tracked) > 10, (
        f"packages/sdk-ts/src 下git 跟踪的文件仅 {len(tracked)} 个，"
        "生成物很可能被 .gitignore 排除——契约漂移将无法检出。"
    )