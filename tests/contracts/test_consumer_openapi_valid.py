"""消费者侧：OpenAPI 规范自身的合法性。

与 `packages/contracts` 的 spectral lint 是**互补**关系，不是重复：

- spectral 用自定义 JSONPath 规则集（.spectral.yaml）管**项目约定**
  （租户头、错误信封、安全声明、kebab-case 路径…），是门禁的一部分，已在CI 跑。
- 本文件用 openapi-spec-validator 管**规范自身是否合法**
  （$ref 能否解析、schema 是否自洽、OpenAPI 3.1 语义），捕捉 spectral 规则集
  覆盖不到的解析层错误——比如 orval 能容忍但运行时会炸的坏 $ref。

这一层必须在「生成 SDK 之前」跑，否则坏契约会先污染生成物再被发现。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

from conftest import CONTRACTS_DIR, OPENAPI_DIR

pytestmark = pytest.mark.consumer

#: AsyncAPI 规范（runtime-events.yaml）不是 OpenAPI，openapi-spec-validator 不适用，
#: 它由 asyncapi CLI 在 contracts 包内校验。此处只列OpenAPI 规范。
OPENAPI_SPECS = ["console-api.yaml", "service-api.yaml"]


@pytest.mark.parametrize("spec", OPENAPI_SPECS)
def test_openapi_spec_is_valid(spec: str) -> None:
    """规范必须通过 OpenAPI 3.1 官方校验（含 $ref 解析与 schema 自洽）。"""
    path = OPENAPI_DIR / spec
    assert path.exists(), f"契约缺失：{path}"
    spec_dict, base_uri = read_from_filename(str(path))
    # base_uri 保留，校验器据此解析 ../schemas/*.yaml 的跨文件 $ref
    validate(spec_dict, base_uri=base_uri)


@pytest.mark.parametrize("spec", OPENAPI_SPECS)
def test_openapi_version_is_31(spec: str) -> None:
    """Phase 0 统一 OpenAPI 3.1（JSON Schema 2020-12）。

    3.0 与 3.1 在 nullable/type 数组等处语义不同，混用会让生成物不一致。
    """
    import yaml

    data = yaml.safe_load((OPENAPI_DIR / spec).read_text(encoding="utf-8"))
    assert str(data.get("openapi", "")).startswith("3.1"), (
        f"{spec} 的 openapi 版本为 {data.get('openapi')}，Phase 0 要求 3.1.x。"
        "版本迁移属于契约变更，请由 Contract Engineer 提工单处理。"
    )


def test_shared_schema_common_yaml_is_valid() -> None:
    """公共 schema 片段自身合法（三份规范共用，单一事实源）。"""
    path = CONTRACTS_DIR / "schemas" / "common.yaml"
    assert path.exists(), f"公共 schema 缺失：{path}"
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data, "common.yaml 解析结果为空或非映射"
    # Error 信封是前端统一错误处理的依赖（铁律的可机检部分）
    err = data.get("Error", {})
    assert set(err.get("required") or []) == {"code", "message", "requestId"}, (
        f"common.yaml#Error 的 required 应为 code/message/requestId，实际为 {err.get('required')}。"
        "破坏此形状会让前端无法做统一错误提示与链路追踪（属于契约变更）。"
    )


def test_contracts_changelog_has_current_version() -> None:
    """契约 CHANGELOG 必须记录当前版本（契约评审的人类检查点留痕）。"""
    import yaml

    version = str(
        yaml.safe_load((OPENAPI_DIR / "console-api.yaml").read_text(encoding="utf-8"))[
            "info"
        ]["version"]
    )
    changelog = (CONTRACTS_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    assert version in changelog, (
        f"console-api 当前版本 {version} 未出现在 packages/contracts/CHANGELOG.md。"
        "契约升版必须写迁移说明（契约评审是人类检查点，QA 负责留痕校验）。"
    )


def test_all_contract_files_have_a_changelog_entry() -> None:
    """每份 OpenAPI 规范的版本都要能被 CHANGELOG 检索到。"""
    import yaml

    changelog = (CONTRACTS_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    missing = []
    for spec in (*OPENAPI_SPECS, "runtime-events.yaml"):
        path = OPENAPI_DIR / spec
        if not path.exists():
            continue
        version = str(
            yaml.safe_load(path.read_text(encoding="utf-8"))["info"]["version"]
        )
        if version not in changelog:
            missing.append(f"{spec}@{version}")
    assert not missing, f"以下契约版本未登记到 CHANGELOG.md：{missing}"


def test_no_absolute_paths_in_contract_refs() -> None:
    """$ref 不得使用绝对路径或 http(s) 远程引用。

    远程 $ref 会让生成与校验依赖网络（CI 不稳定）；绝对路径换机器即断。
    两者都属于契约卫生问题，发现即上报 Contract Engineer。
    """
    offenders: list[str] = []
    for path in sorted(OPENAPI_DIR.glob("*.yaml")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "$ref:" not in line:
                continue
            value = line.split("$ref:", 1)[1].strip()
            if value.startswith(("http://", "https://", "/", "file://")):
                offenders.append(f"{path.name}:{lineno} -> {value}")
    assert not offenders, (
        f"契约中存在非法 $ref（远程或绝对路径）：{offenders}。"
        "远程 $ref 使生成依赖网络，绝对路径不可移植——请改为仓内相对路径。"
    )


def test_contract_files_are_tracked_in_git() -> None:
    """契约必须被 git 跟踪（契约先行的物理前提）。"""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "packages/contracts/openapi"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert len(tracked) >= 3, (
        f"packages/contracts/openapi 下git 跟踪的文件仅 {len(tracked)} 个，"
        "契约可能未被提交——契约不落盘则一切校验都是空转。"
    )