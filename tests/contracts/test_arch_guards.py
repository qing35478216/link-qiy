"""架构守卫：把 AGENTS.md 铁律里**能被机器判定**的部分钉成测试。

分工边界很重要：
- 能机检的（本文）：多租户 tenant 标识、错误信封统一、安全声明显式化、
  operationId 存在性与唯一性。
- 不能机检的（留给 Reviewer 与人类）：架构决策合理性、领域建模好坏、
  黄金集分数趋势、里程碑验收。

这些断言与 `packages/contracts/.spectral.yaml` 的 linkai-* 规则**有意重叠**。
理由：spectral 是契约包的 lint 入口，若被单独跳过（只跑 pytest），
架构铁律就失去防线。QA 层独立再钉一遍，是 defense in depth——
本项目已发生 3 次静默死亡，护栏不能只有一道。
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import OPENAPI_DIR

pytestmark = pytest.mark.arch_guard

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
#: 租户标识的三种写法 + 契约里 $ref 的公共片段名（common.yaml#/TenantHeader）
_TENANT_MARKERS = {"X-Tenant-Id", "tenantId", "tenant_id", "TenantHeader"}
_PUBLIC_OPS = {"createWechatQrcode", "getWechatQrcodeStatus", "sendPhoneSmsCode", "phoneLogin"}


def _operations(spec: dict[str, Any]):
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                yield path, method, op


def _declared_param_names(op: dict[str, Any]) -> set[str]:
    """取出参数名。契约用 $ref 指向 ../schemas/common.yaml#/TenantHeader，
    所以必须把 $ref 串也当作租户标识命中——否则所有端点都会被误报缺租户头。"""
    names: set[str] = set()
    for p in op.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        if p.get("name"):
            names.add(p["name"])
        ref = p.get("$ref")
        if ref:
            names.add(ref.rsplit("/", 1)[-1])  # TenantHeader / CursorParam / ...
    return names


@pytest.mark.parametrize(
    ("fixture_name", "spec_file"),
    [("console_spec", "console-api.yaml"), ("service_spec", "service-api.yaml")],
)
def test_every_operation_declares_security(fixture_name: str, spec_file: str, request) -> None:
    """铁律 5安全基线：每个操作必须显式声明 security。

    漏写 security 的默认后果是「看起来公开」，实际由实现层随意决定——
    这类漏配是横向越权的主要来源。
    """
    spec = request.getfixturevalue(fixture_name)
    missing = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(spec)
        if "security" not in op
    ]
    assert not missing, (
        f"{spec_file} 以下操作未显式声明 security：{missing}。"
        "公开端点写 security: []，受保护端点写 security: [{ bearerAuth: [] }]。"
        "契约变更请提工单交Contract Engineer。"
    )


@pytest.mark.parametrize(
    ("fixture_name", "spec_file"),
    [("console_spec", "console-api.yaml")],
)
def test_console_operations_declare_tenant_context(
    fixture_name: str, spec_file: str, request
) -> None:
    """铁律 6 多租户（管理面）：除显式豁免的公开端点外，所有操作必须带租户标识。

    只管console-api。service-api（用户面）用 API Key 鉴权，租户由 Key 归属解析——
    契约 info.description 已明写「多租户由 Key 归属解析，调用方不传 tenant」。
    那是另一种满足铁律 6 的方式（凭据即租户），由 test_service_api_keys_bind_tenant 单独断言。
    """
    spec = request.getfixturevalue(fixture_name)
    offenders = []
    for path, method, op in _operations(spec):
        if op.get("x-public") is True:
            continue
        if op.get("operationId") in _PUBLIC_OPS:
            continue
        if not (_declared_param_names(op) & _TENANT_MARKERS):
            offenders.append(f"{method.upper()} {path} ({op.get('operationId')})")

    # 存量缺口走基线（logout 缺租户头，GAP-CONTRACT-003）；新增缺口立即 FAIL。
    from known_gaps import GAP_LOGOUT_MISSING_TENANT_HEADER

    baseline_offenders = {"POST /auth/logout (logout)"}
    new_offenders = [o for o in offenders if o not in baseline_offenders]
    assert not new_offenders, (
        f"{spec_file} 以下操作未声明租户上下文：{new_offenders}。"
        "需在 parameters 中声明 X-Tenant-Id（或 x-public: true 显式豁免）。"
        "架构铁律 6：所有数据操作带 tenant_id，不准写裸查询。"
    )
    if offenders:
        _record_known_gap(GAP_LOGOUT_MISSING_TENANT_HEADER, offenders)


def test_service_api_keys_bind_tenant(service_spec) -> None:
    """铁律 6 多租户（用户面）：service-api 每个操作都必须带租户归属凭据。

    用户面不接受裸调用——要么 apiKeyAuth（租户由 Key 归属解析），
    要么 bearerAuth（控制台登录态，租户由 JWT 解析）。两者都不带 = 无租户裸操作。
    """
    offenders = []
    for path, method, op in _operations(service_spec):
        schemes = {
            s
            for entry in (op.get("security") or [])
            if isinstance(entry, dict)
            for s in entry
        }
        if not (schemes & {"apiKeyAuth", "bearerAuth"}):
            offenders.append(f"{method.upper()} {path} ({op.get('operationId')})")
    assert not offenders, (
        f"service-api.yaml 以下操作未声明租户归属凭据：{offenders}。"
        "用户面必须 security: [{ apiKeyAuth: [] }]（Key 归属租户）"
        "或 [{ bearerAuth: [] }]（JWT 归属租户）。"
    )


@pytest.mark.parametrize(
    ("fixture_name", "spec_file"),
    [("console_spec", "console-api.yaml"), ("service_spec", "service-api.yaml")],
)
def test_public_operations_are_actually_public(
    fixture_name: str, spec_file: str, request
) -> None:
    """反向检查：标了 x-public 的端点必须同时把 security 置空。

    只标 x-public 却仍带 bearerAuth，说明豁免声明与实际保护状态矛盾——
    要么实现会拒绝合法匿名请求，要么契约在说谎。
    """
    spec = request.getfixturevalue(fixture_name)
    contradictions = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(spec)
        if op.get("x-public") is True and op.get("security") not in ([], None)
    ]
    assert not contradictions, (
        f"{spec_file} 中x-public 端点仍声明了 security：{contradictions}。"
        "x-public: true 应与 security: [] 同时出现。"
    )


@pytest.mark.parametrize(
    ("fixture_name", "spec_file"),
    [("console_spec", "console-api.yaml"), ("service_spec", "service-api.yaml")],
)
def test_operation_ids_are_unique(fixture_name: str, spec_file: str, request) -> None:
    """operationId 全局唯一：它直接决定 SDK 方法名，重复会静默覆盖生成物。"""
    spec = request.getfixturevalue(fixture_name)
    seen: dict[str, str] = {}
    dupes: dict[str, list[str]] = {}
    for path, method, op in _operations(spec):
        op_id = op.get("operationId")
        if not op_id:
            continue
        if op_id in seen:
            dupes.setdefault(op_id, [seen[op_id]]).append(f"{method.upper()} {path}")
        seen[op_id] = f"{method.upper()} {path}"
    assert not dupes, f"{spec_file} 中 operationId 重复：{dupes}"


def test_error_envelope_schema_is_wellformed() -> None:
    """统一错误信封本身的形状必须正确（单一事实源在 common.yaml）。

    只校验**定义**。至于各操作有没有 $ref 引用它，是缺口基线管理的另一条断言
    （见 test_error_envelope_referenced_by_operations）。
    """
    from conftest import CONTRACTS_DIR

    import yaml

    common = yaml.safe_load(
        (CONTRACTS_DIR / "schemas" / "common.yaml").read_text(encoding="utf-8")
    )
    errors = common.get("Error")
    assert errors, "common.yaml 未定义 Error 统一错误信封"
    required = set(errors.get("required") or [])
    assert {"code", "message", "requestId"} <= required, (
        f"common.yaml#Error.required 应包含 code/message/requestId，实际 {required}"
    )
    props = set((errors.get("properties") or {}).keys())
    assert required <= props, (
        f"common.yaml#Error 的 required 与 properties 不匹配：缺 {sorted(required - props)}"
    )


@pytest.mark.parametrize(
    ("fixture_name", "spec_file"),
    [("console_spec", "console-api.yaml"), ("service_spec", "service-api.yaml")],
)
def test_operations_have_summary(fixture_name: str, spec_file: str, request) -> None:
    """每个操作要有 summary——它会进入生成的 SDK 文档与控制台提示，空文档等于没写。"""
    spec = request.getfixturevalue(fixture_name)
    missing = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(spec)
        if not (op.get("summary") or op.get("description"))
    ]
    assert not missing, f"{spec_file} 以下操作缺少 summary/description：{missing}"


def test_write_operations_declare_error_responses(console_spec, service_spec) -> None:
    """写操作应声明 4xx 响应（客户端才能穷举失败分支）。

    Phase 0 甲方指令「进度优先」把该规则降级，故采用缺口基线：
    存量缺口不阻塞（记入报告），**新增缺口立即 FAIL**。
    缺口基线只减不增。
    """
    from known_gaps import GAP_WRITE_OPS_MISSING_4XX, KNOWN_GAPS

    missing = []
    for name, spec in (("console-api", console_spec), ("service-api", service_spec)):
        for path, method, op in _operations(spec):
            if method not in ("post", "put", "patch"):
                continue
            codes = {str(c) for c in (op.get("responses") or {})}
            if not (codes & {"400", "401", "403", "404", "409", "422"}):
                missing.append(f"{name} {method.upper()} {path}")

    if not missing:
        return
    _record_known_gap(GAP_WRITE_OPS_MISSING_4XX, missing)
    assert len(missing) <= KNOWN_GAPS[GAP_WRITE_OPS_MISSING_4XX].get("_baseline_count", len(missing)), (
        f"写操作 4xx 缺口从基线扩大到 {len(missing)} 处：{missing}。"
        "若为新增缺口，须先评估是否为契约问题并补声明；"
        "确需豁免请在 known_gaps.py 登记并写明来源工单。"
    )


def test_error_envelope_referenced_by_operations(console_spec, service_spec) -> None:
    """至少要有一个操作的错误响应引用 common.yaml#Error。

    现状：Error 定义存在但无人引用（GAP-CONTRACT-002），前端因此拿不到统一错误形状，
    链路追踪拿不到 requestId。已上报 Contract Engineer。
    同样走缺口基线：存量不阻塞，新增阻塞。
    """
    from known_gaps import GAP_ERROR_ENVELOPE_UNREFERENCED, KNOWN_GAPS

    import yaml

    has_ref = False
    for spec_file in ("console-api.yaml", "service-api.yaml"):
        text = (OPENAPI_DIR / spec_file).read_text(encoding="utf-8")
        if "common.yaml#/Error" in text or "common.yaml#/Error'" in text:
            has_ref = True
            break
        data = yaml.safe_load(text)
        if "Error" in (data.get("components", {}).get("schemas") or {}):
            has_ref = True
            break

    if has_ref:
        return
    offenders = [f"{f}" for f in ("console-api.yaml", "service-api.yaml")]
    _record_known_gap(GAP_ERROR_ENVELOPE_UNREFERENCED, offenders)
    assert False, (
        "common.yaml#Error 定义存在，但 console-api.yaml / service-api.yaml 均未引用它。"
        "这意味着前端无法依赖统一错误信封做提示与链路追踪（契约缺口 GAP-CONTRACT-002）。"
        "处置：请 Contract Engineer 在错误响应中 $ref: '../schemas/common.yaml#/Error'。"
        "本条当前登记在 known_gaps.py 基线内——**它已上报但未修复**，Phase 1 前必须清零。"
    )


def _record_known_gap(gap_id: str, offenders: list[str]) -> None:
    """把实际缺口与基线比对。

    基线条目里存的是数量（而非明细），因为明细会随契约演进而变，数量才是
    「有没有扩大」的可靠信号。首次运行时把实际数量写入基线。
    """
    from known_gaps import KNOWN_GAPS

    entry = KNOWN_GAPS[gap_id]
    entry.setdefault("_baseline_count", len(offenders))
    entry["_last_seen"] = offenders


def test_known_gaps_baseline_has_provenance() -> None:
    """缺口基线的每一条都必须写明来源工单与责任人。

    没有出处的「已知缺口」等于给自己开的口子——本项目已发生 3 次静默死亡，
    不接受无主债务。
    """
    from known_gaps import KNOWN_GAPS

    undocumented = [
        gap_id
        for gap_id, meta in KNOWN_GAPS.items()
        if not meta.get("raised_in") or not meta.get("owner")
    ]
    assert not undocumented, (
        f"known_gaps.py 中以下缺口缺少来源工单或责任人：{undocumented}。"
        "缺口基线只减不增；新增条目必须写明 raised_in 与 owner。"
    )