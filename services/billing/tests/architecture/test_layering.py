"""架构铁律的自动化守卫（铁律 2 + 工单 Self-Check：domain 层无框架依赖）。

与 platform 同款守卫（AST 静态解析，防 `import fastapi as f` / 延迟导入绕过）：
1. domain 层零框架 import（只准标准库 + 本层模块）；
2. 依赖方向只向内：services 不准 import api；domain 不准 import services/api/infra；
3. **services 层零框架 import**（资金域加严：Session/IntegrityError 等驱动
   异常不准跨层——仓储以布尔/领域错误回传，应用层不碰 sqlalchemy）；
4. ORM 模型只出现在 infra（铁律 2）。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "linkai_billing"
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
    }
)

# services 层同样禁止框架/驱动 import（比 platform 更严：资金域）
FORBIDDEN_IN_SERVICES = FORBIDDEN_IN_DOMAIN

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
    assert _module_files(layer), f"{layer} 层没有任何源文件，守卫会假通过"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_only_imports_stdlib_or_own_layer(path: Path) -> None:
    external: set[str] = set()
    for root in _imported_roots(path):
        if root == "linkai_billing":
            continue
        if root not in _STDLIB:
            external.add(root)
    assert not external, f"{path.name} 导入了非标准库模块 {sorted(external)}"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_does_not_import_outer_layers(path: Path) -> None:
    offenders = {
        module
        for module in _absolute_from_imports(path)
        if module.startswith("linkai_billing.")
        and module.split(".")[1:2]
        and module.split(".")[1] in {"api", "services", "infra"}
    }
    assert not offenders, f"{path.name} 反向依赖外层 {sorted(offenders)}（依赖只准向内）"


@pytest.mark.parametrize("path", _module_files("services"), ids=lambda p: p.name)
def test_services_does_not_import_api(path: Path) -> None:
    offenders = {
        module
        for module in _absolute_from_imports(path)
        if module.startswith("linkai_billing.api")
    }
    assert not offenders, f"{path.name} 反向依赖 api 层 {sorted(offenders)}"


@pytest.mark.parametrize("path", _module_files("services"), ids=lambda p: p.name)
def test_services_has_no_framework_import(path: Path) -> None:
    """资金域加严：services 不碰 sqlalchemy/fastapi 等（驱动细节留在 infra）。"""
    offenders = sorted(_imported_roots(path) & FORBIDDEN_IN_SERVICES)
    assert not offenders, f"{path.name} 引入了框架依赖 {offenders}（驱动细节只准在 infra）"


@pytest.mark.parametrize("layer", ["api", "services", "domain"])
def test_orm_models_only_defined_in_infra(layer: str) -> None:
    offenders = [
        p.name
        for p in _module_files(layer)
        if "linkai_billing.infra.models" in _referenced_modules(p)
    ]
    assert not offenders, f"{layer} 层直接引用了 ORM 模型：{offenders}（ORM 模型只准在 infra）"
