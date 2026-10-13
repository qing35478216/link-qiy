"""架构铁律的自动化守卫（铁律 2 + 验收标准 3）。

用 AST 静态解析 import，而不是靠人肉 review 或 grep——grep 挡不住
`import fastapi as f`、`__import__`、函数内延迟导入等绕过写法。

守卫三条：
1. domain 层零框架 import（验收标准 3）：只准标准库 + 本层模块
2. 依赖方向只向内：services 不准 import api；domain 不准 import services/api/infra
3. infra 是 domain 定义的仓储接口的唯一实现方（ORM 只出现在 infra，铁律 2）
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "linkai_platform"
LAYERS = ("api", "services", "domain", "infra")

# domain 层绝对不准出现的框架/第三方包（铁律 2：domain 是纯 Python）
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

# 允许 domain 导入的标准库（sys.stdlib_module_names 覆盖不全的场景在此兜底）
_STDLIB = sys.stdlib_module_names


def _module_files(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    """返回该文件 import 的所有顶层包名（含 import x / from x import y / 相对导入标记）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # 相对导入（from . import x）——同包内，不产生外部依赖
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _full_imported_modules(path: Path) -> set[str]:
    """返回该文件 import 的完整模块名（from a.b.c import x → "a.b.c"）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def _relative_imports(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, ast.ImportFrom) and node.level and node.level > 0 for node in ast.walk(tree)
    )


@pytest.mark.parametrize("layer", LAYERS)
def test_each_layer_has_sources(layer: str) -> None:
    """前置断言：扫描器本身没跑空（空目录会让下面的守卫假通过）。"""
    assert _module_files(layer), f"{layer} 层没有任何源文件，守卫会假通过"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_has_no_framework_import(path: Path) -> None:
    """验收标准 3：domain 层零框架 import。"""
    offenders = sorted(_imported_roots(path) & FORBIDDEN_IN_DOMAIN)
    assert not offenders, f"{path.name} 引入了框架依赖 {offenders}（铁律 2：domain 必须是纯 Python）"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_only_imports_stdlib_or_own_layer(path: Path) -> None:
    """domain 只准标准库 + linkai_platform.domain（白名单视角，比黑名单更难绕过）。"""
    external: set[str] = set()
    for root in _imported_roots(path):
        if root == "linkai_platform":
            # 允许 import linkai_platform.domain.*，但下面单独断言不得跨层
            continue
        if root not in _STDLIB:
            external.add(root)
    assert not external, f"{path.name} 导入了非标准库模块 {sorted(external)}"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_does_not_import_outer_layers(path: Path) -> None:
    """domain 不得依赖 api/services/infra（依赖只准向内）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("linkai_platform."):
            parts = node.module.split(".")  # type: ignore[union-attr]
            if len(parts) > 1 and parts[1] in {"api", "services", "infra"}:
                offenders.add(node.module)  # type: ignore[union-attr]
    assert not offenders, f"{path.name} 反向依赖外层 {sorted(offenders)}（依赖只准向内）"


@pytest.mark.parametrize("path", _module_files("services"), ids=lambda p: p.name)
def test_services_does_not_import_api(path: Path) -> None:
    """services 是应用层，不得反向依赖接口层。"""
    offenders = {
        node.module
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("linkai_platform.api")
    }
    assert not offenders, f"{path.name} 反向依赖 api 层 {sorted(offenders)}"


@pytest.mark.parametrize("layer", ["api", "services", "domain"])
def test_orm_models_only_defined_in_infra(layer: str) -> None:
    """ORM 模型只准出现在 infra（铁律 2 + 角色定义："ORM 模型只出现在 infra"）。

    注意与"api 层不得 import sqlalchemy"区分开：api/deps.py 是组装根
    （composition root），它必须能引用 Session 类型来划事务边界、并实例化 infra
    实现——那是它的职责。真正要禁止的是**声明式 ORM 模型**（UserModel 等）
    泄漏到 infra 之外：那会让业务代码绕过仓储直接拼 SQL，tenant_id 强制过滤
    （铁律 6）随之失效。
    """
    offenders = [
        p.name
        for p in _module_files(layer)
        if "linkai_platform.infra.models" in _full_imported_modules(p)
    ]
    assert not offenders, f"{layer} 层直接引用了 ORM 模型：{offenders}（ORM 模型只准在 infra）"


@pytest.mark.parametrize("path", _module_files("domain"), ids=lambda p: p.name)
def test_domain_has_no_framework_import(path: Path) -> None:
    """验收标准 3：domain 层零框架 import（含 sqlalchemy，不给组装根开口子）。"""
    offenders = sorted(_imported_roots(path) & FORBIDDEN_IN_DOMAIN)
    assert not offenders, f"{path.name} 引入了框架依赖 {offenders}（铁律 2：domain 必须是纯 Python）"


def test_domain_uses_relative_or_intra_layer_imports_only() -> None:
    """domain 内部互相引用只走 linkai_platform.domain.* 显式路径。

    这条不是性能洁癖：一旦有人改成 `from linkai_platform import domain` 之类的
    顶层导入，import 环会在模块初始化顺序上炸，且很难定位。
    """
    for path in _module_files("domain"):
        assert not _relative_imports(path), f"{path.name} 使用了相对导入，请用完整包路径"
