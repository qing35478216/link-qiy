"""架构守卫——用 AST 扫描强制铁律，不靠人自觉。

守护的规则：
- 铁律 2：domain 层不得 import 任何框架/基础设施；
- 铁律 2：依赖只准向内（domain 不许 import services/api/infra，反之亦然）；
- 铁律 5：厂商出网只准走 infra/http_client.py（业务代码不得直接 import httpx）；
- 铁律 4：内核不得出现具体厂商名硬分支。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "linkai_model_proxy"

#: 框架/第三方根模块——domain 层出现任何一个即违规
FORBIDDEN_IN_DOMAIN = {
    # web 框架
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    # 出网
    "httpx",
    "httpcore",
    "aiohttp",
    "requests",
    "urllib3",
    # 数据/存储
    "sqlalchemy",
    "alembic",
    "redis",
    "psycopg",
    "celery",
    # 云厂商 SDK（应当经适配器走 HTTP，见 ADOPTED-TOOLS.md §2）
    "openai",
    "anthropic",
    "dashscope",
    "zhipuai",
    # 可观测与日志
    "structlog",
    "opentelemetry",
}

#: 允许的根模块（标准库 + typing 扩展）
ALLOWED_STDLIB_PREFIXES = {
    "abc",
    "asyncio",
    "collections",
    "contextlib",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "hashlib",
    "ipaddress",
    "json",
    "math",
    "re",
    "socket",
    "time",
    "types",
    "typing",
    "uuid",
    "warnings",
    "__future__",
    "os",
    "logging",
    "itertools",
    "string",
}


def _module_name(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.Import):
        return node.names[0].name.split(".")[0]
    assert isinstance(node, ast.ImportFrom)
    return (node.module or "").split(".")[0]


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [_module_name(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]


def _py_files(layer: str) -> list[Path]:
    return sorted((SRC / layer).rglob("*.py"))


class TestDomainLayerPurity:
    """铁律 2：domain 层是纯 Python。"""

    def test_domain_imports_no_framework(self) -> None:
        offenders: list[str] = []
        for path in _py_files("domain"):
            for name in _imports(path):
                if name in FORBIDDEN_IN_DOMAIN:
                    offenders.append(f"{path.name} -> {name}")
        assert not offenders, f"domain 层出现框架依赖：{offenders}"

    def test_domain_imports_only_stdlib(self) -> None:
        offenders: list[str] = []
        for path in _py_files("domain"):
            for name in _imports(path):
                if name.startswith("linkai_model_proxy"):
                    continue
                if name not in ALLOWED_STDLIB_PREFIXES:
                    offenders.append(f"{path.name} -> {name}")
        assert not offenders, f"domain 层引入了非白名单模块：{offenders}"


class TestLayerDependencyDirection:
    """铁律 2：依赖只准向内。"""

    def test_domain_does_not_import_outward(self) -> None:
        offenders: list[str] = []
        for path in _py_files("domain"):
            text = path.read_text(encoding="utf-8")
            for forbidden in (
                "linkai_model_proxy.api",
                "linkai_model_proxy.services",
                "linkai_model_proxy.infra",
            ):
                if forbidden in text:
                    offenders.append(f"{path.name} -> {forbidden}")
        assert not offenders, f"domain 层向外依赖：{offenders}"

    def test_services_does_not_import_api(self) -> None:
        offenders: list[str] = []
        for path in _py_files("services"):
            text = path.read_text(encoding="utf-8")
            if "linkai_model_proxy.api" in text:
                offenders.append(path.name)
        assert not offenders, f"services 反向依赖 api：{offenders}"

    def test_api_does_not_import_infra_directly(self) -> None:
        """api 层只做协议转换，基础设施访问应经 dependencies.py 收敛。

        豁免 `api/dependencies.py`（它就是装配点）与 `api/routers/health.py`
        （自省注册中心需要读协议分类，属只读元数据）。
        """
        allowed = {"dependencies.py", "health.py"}
        offenders: list[str] = []
        for path in _py_files("api"):
            if path.name in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            if "linkai_model_proxy.infra" in text:
                offenders.append(path.name)
        assert not offenders, f"api 层直连infra：{offenders}"


class TestEgressGuard:
    """铁律 5：厂商出网只准走 infra/http_client.py。"""

    #: 允许直接 import httpx 的文件（装配/自省用途，不发请求）
    HTTPX_ALLOWED: ClassVar[frozenset[str]] = frozenset(
        {"http_client.py", "dependencies.py", "health.py"}
    )

    def _all_source_files(self) -> list[Path]:
        return sorted(p for p in SRC.rglob("*.py") if p.name != "__init__.py")

    def test_only_whitelisted_files_import_httpx(self) -> None:
        """任何直接 import httpx 的文件都必须在白名单里。

        适配器与业务层若绕过 http_client 直接用 httpx，
        SSRF 闸门就会被跳过——这是本服务最关键的安全约束。
        """
        offenders = [
            str(p.relative_to(SRC))
            for p in self._all_source_files()
            if p.name not in self.HTTPX_ALLOWED and "httpx" in _imports(p)
        ]
        assert not offenders, f"绕过 http_client 直连 httpx：{offenders}"

    def test_adapters_never_import_httpx(self) -> None:
        """适配器只能用 VendorHttpClient——保证请求一定过 SSRF 闸门。"""
        offenders = [
            p.name
            for p in sorted((SRC / "infra" / "adapters").rglob("*.py"))
            if "httpx" in _imports(p)
        ]
        assert not offenders, f"适配器直接 import httpx（会绕过 SSRF 闸门）：{offenders}"


class TestNoVendorHardcodingInKernel:
    """铁律 4：新增厂商不改内核。"""

    VENDORS: ClassVar[frozenset[str]] = frozenset(
        {"openai", "anthropic", "deepseek", "qwen", "glm"}
    )

    def test_no_vendor_string_comparison_in_inner_layers(self) -> None:
        offenders: list[str] = []
        for layer in ("domain", "services"):
            for path in _py_files(layer):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Compare):
                        operands = [node.left, *node.comparators]
                        for operand in operands:
                            if (
                                isinstance(operand, ast.Constant)
                                and isinstance(operand.value, str)
                                and operand.value in self.VENDORS
                            ):
                                offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, f"内核出现厂商硬分支：{offenders}"


class TestNoHardcodedSecrets:
    """安全基线：源码里不得出现疑似真实密钥。"""

    def test_no_provider_key_literals(self) -> None:
        import re

        # 真实厂商 Key 前缀（sk- / sk-ant- 后面跟足够长的随机串）
        pattern = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.relative_to(SRC)}: {match.group()[:12]}...")
        assert not offenders, f"疑似硬编码密钥：{offenders}"


@pytest.mark.parametrize("layer", ["domain", "services", "api", "infra"])
def test_layer_exists(layer: str) -> None:
    """四层目录齐备（docs/03 §3.1）。"""
    assert (SRC / layer).is_dir()
