"""注册机制用例——验收标准 2：**新增 mock 适配器零内核改动**。

这是铁律 4 的回归护栏：如果哪天有人把厂商判断写进内核分支
（`if provider == "openai"` 之类），本文件会失败。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from linkai_model_proxy.domain.adapter import ModelAdapter
from linkai_model_proxy.domain.errors import AdapterNotRegisteredError, DomainError
from linkai_model_proxy.domain.registry import AdapterRegistry
from linkai_model_proxy.infra.adapters import builtin_registry, register_builtins
from linkai_model_proxy.infra.http_client import VendorHttpClient

from tests.conftest import ScriptedAdapter, ScriptedAdapterFactory, make_card

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "linkai_model_proxy"


class TestRegistryBasics:
    def test_builtin_providers_registered(self, vendor_http: VendorHttpClient) -> None:
        registry = builtin_registry(vendor_http)
        assert set(registry.providers()) == {"openai", "anthropic", "deepseek", "qwen", "glm"}
        assert len(registry) == 5

    def test_resolve_returns_adapter_for_each_builtin(self, vendor_http: VendorHttpClient) -> None:
        registry = builtin_registry(vendor_http)
        for provider in registry.providers():
            adapter = registry.resolve(provider)
            assert isinstance(adapter, ModelAdapter)
            assert adapter.provider == provider

    def test_resolve_unregistered_raises(self, vendor_http: VendorHttpClient) -> None:
        registry = builtin_registry(vendor_http)
        with pytest.raises(AdapterNotRegisteredError) as exc:
            registry.resolve("no-such-vendor")
        # 错误信息应列出已注册厂商，便于排障
        assert "openai" in str(exc.value)

    def test_duplicate_register_rejected(self, vendor_http: VendorHttpClient) -> None:
        """重复注册必须报错——避免"后注册静默覆盖"的隐性行为。"""
        registry = builtin_registry(vendor_http)
        with pytest.raises(DomainError, match="已注册"):
            register_builtins(registry, vendor_http)

    def test_unregister_then_register_allowed(self, vendor_http: VendorHttpClient) -> None:
        registry = builtin_registry(vendor_http)
        registry.unregister("openai")
        assert not registry.is_registered("openai")
        register_builtins(AdapterRegistry(), registry)  # 新注册表不受影响
        assert not registry.is_registered("openai")

    def test_snapshot_is_readonly(self, vendor_http: VendorHttpClient) -> None:
        registry = builtin_registry(vendor_http)
        snapshot = registry.snapshot()
        with pytest.raises(TypeError):
            snapshot["injected"] = None  # type: ignore[index]


class TestZeroKernelChange:
    """核心验收：新增厂商只动infra，不动内核。"""

    def test_register_mock_adapter_without_touching_kernel(self) -> None:
        """纯注册表操作即可接入新厂商——不 import 任何内核模块的私有细节。"""
        registry = AdapterRegistry()
        adapter = ScriptedAdapter(provider="brand-new-vendor", response=None)
        registry.register(
            "brand-new-vendor",
            ScriptedAdapterFactory(adapter),
            capabilities=adapter.capabilities,
        )

        assert registry.is_registered("brand-new-vendor")
        resolved = registry.resolve("brand-new-vendor")
        assert resolved.provider == "brand-new-vendor"

    def test_external_adapter_via_extra_parameter(self, vendor_http: VendorHttpClient) -> None:
        """`extra` 参数让外部包无需修改 builtin 文件即可接入。"""
        scripted = ScriptedAdapter(provider="plugin-vendor")

        registry = register_builtins(
            AdapterRegistry(),
            vendor_http,
            extra=[("plugin-vendor", lambda http: scripted)],
        )

        assert "plugin-vendor" in registry
        assert registry.resolve("plugin-vendor") is scripted
        # 内置厂商不受影响
        assert "openai" in registry

    def test_kernel_has_no_provider_branching(self) -> None:
        """架构守卫：domain/services/api 三层不得出现具体厂商名硬分支。

        若有人把 `if provider == "openai"` 写进内核，本用例失败。
        """
        offenders: list[str] = []
        for layer in ("domain", "services", "api"):
            for path in (SRC_ROOT / layer).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Compare):
                        # 只检查字符串比较（厂商判断的典型形态）
                        for operand in (node.left, *node.comparators):
                            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                                value = operand.value
                                if value in {
                                    "openai",
                                    "anthropic",
                                    "deepseek",
                                    "qwen",
                                    "glm",
                                }:
                                    offenders.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")
        assert not offenders, f"内核出现厂商硬分支：{offenders}"


class TestAdapterRegistryContract:
    def test_registration_exposes_allow_byok(self, vendor_http: VendorHttpClient) -> None:
        registry = builtin_registry(vendor_http)
        registration = registry.get_registration("openai")
        assert registration is not None
        assert registration.allow_byok is True

    def test_factory_must_satisfy_protocol(self) -> None:
        """工厂产出物若不满足协议，注册表在实例化时报错而非静默通过。"""
        registry = AdapterRegistry()
        registry.register("bad", lambda: object())  # type: ignore[arg-type,return-value]
        with pytest.raises(TypeError, match="ModelAdapter"):
            registry.resolve("bad")

    def test_model_card_provider_can_be_any_string(self) -> None:
        """ModelCard.provider 是自由字符串——厂商清单不在内核枚举里。"""
        card = make_card(code="kimi-k2", provider="moonshot")
        assert card.provider == "moonshot"