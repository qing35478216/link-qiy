"""架构铁律的自动化守卫（铁律 2 + 工单 Self-Check，与 platform 同构）。

AST 静态解析 import（grep 挡不住 `import fastapi as f` / 延迟导入等绕过）：
1. domain 层零框架 import（Self-Check：domain 无框架依赖）
2. 依赖方向只向内：services 不准 import api；domain 不准 import services/api/infra
3. ORM 模型只出现在 infra（铁律 2）
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "linkai_runtime"
LAYERS = ("api", "services", "domain", "infra")

FORBIDDEN_IN_DOMAIN = frozenset(
    {
        "fastapi",
        "starlette",
        "pydantic",
        "sqlalchemy",
        "alembic",
        "jwt",
        "structlog",
        "redis",
        "psycopg",
        "opentelemetry",
        "httpx",
        "pydantic_settings",
    }
)

_STDLIB = sys.stdlib_module_names


def _module_files(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _absolute_from_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and not node.level
    ]


def _referenced_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = set(_absolute_from_imports(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


@pytest.mark.parametrize("layer", LAYERS)
def test_each_layer_has_sources(layer: str) -> None:
    """前置断言：扫描器没跑空（空目录会让守卫假通过）。"""
    assert _module_files(layer), f"{layer} 层没有任何源文件，守卫会假通过"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_only_imports_stdlib_or_own_layer(path: Path) -> None:
    external = {
        root for root in _imported_roots(path) if root != "linkai_runtime" and root not in _STDLIB
    }
    assert not external, f"{path.name} 导入了非标准库模块 {sorted(external)}"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_does_not_import_outer_layers(path: Path) -> None:
    offenders = {
        module
        for module in _absolute_from_imports(path)
        if module.startswith("linkai_runtime.")
        and module.split(".")[1:2]
        and module.split(".")[1] in {"api", "services", "infra"}
    }
    assert not offenders, f"{path.name} 反向依赖外层 {sorted(offenders)}（依赖只准向内）"


@pytest.mark.parametrize("path", _module_files("services"), ids=lambda p: p.name)
def test_services_does_not_import_api(path: Path) -> None:
    offenders = {
        module for module in _absolute_from_imports(path) if module.startswith("linkai_runtime.api")
    }
    assert not offenders, f"{path.name} 反向依赖 api 层 {sorted(offenders)}"


@pytest.mark.parametrize("layer", ["api", "services", "domain"])
def test_orm_models_only_defined_in_infra(layer: str) -> None:
    offenders = [
        p.name
        for p in _module_files(layer)
        if "linkai_runtime.infra.models" in _referenced_modules(p)
    ]
    assert not offenders, f"{layer} 层直接引用了 ORM 模型：{offenders}（ORM 模型只准在 infra）"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_has_no_framework_import(path: Path) -> None:
    offenders = sorted(_imported_roots(path) & FORBIDDEN_IN_DOMAIN)
    assert not offenders, f"{path.name} 引入了框架依赖 {offenders}（铁律 2：domain 须纯 Python）"
