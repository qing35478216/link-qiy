"""架构守卫：把 AGENTS.md 铁律里**能被机器判定**的部分钉成测试。

## 分工边界（与 `.spectral.yaml` 的划界，勿再扩大重叠）

主理人裁决（T-010评审）：**spectral 管 lint 规则，本文件管 spectral 表达不了的规则。**
「重复不叫纵深，叫维护负担」——契约改动需两处同改，漏改概率远高于「有人显式跳过
spectral」（前者静默腐化，后者是显式行为）。

按此原则，本文件**只保留 spectral 无法或不应表达的规则**：

| 本文件的规则 | 为什么留在 pytest |
|---|---|
| `test_console_operations_declare_tenant_context` | 需解析 `$ref`（`../schemas/common.yaml#/TenantHeader`）并跨文件比对；spectral 的 JSONPath 看不见被引用文件里的 `name: X-Tenant-Id` |
| `test_service_api_keys_bind_tenant` | 判定依据是「用户面租户由 Key 归属解析」这一**跨规范语义约定**，需对比两份规范的 security 方案，不是单份规范的结构校验 |
| `test_public_operations_are_actually_public` | `x-public: true` 与 `security: []` 的**矛盾检测**（两者都写了但不一致）。spectral 逐规则判断，天然做不了跨字段一致性检查 |
| `test_operation_ids_are_unique` | 已迁回 spectral（见下方迁出记录），此处不再断言 |
| `test_login_paths_agreement_consistency` | **跨端点一致性检测**：取约束最严的登录通道作基准，比对其他通道。与 spectral 的「逐操作独立判断」是不同范式——spectral 无法表达「A 与 B 要一致」 |
| `test_error_envelope_referenced_by_operations` | 检测**跨文件引用是否存在**（$ref 有没有被用上）。spectral 校验 $ref 写得对不对，不校验它有没有被引用 |
| `test_known_gaps_baseline_has_provenance` | 检查 `known_gaps.py` 自身的元数据完整性，与契约内容无关 |
| `test_contracts/*` 其余用例 | 规范合法性、生成物漂移——spectral 完全不覆盖 |

## 迁出记录（迁回 spectral 的规则，防再次重复实现）

- **2026-10-13**：`test_operation_ids_are_unique` →已由
  `.spectral.yaml` 的 `operation-operationId-unique: error` 覆盖，从本文件移除。
  原因：spectral 的 `spectral:oas` 规则集自带该检查且已是 error 级，
  我们再写一遍纯属重复维护。
- **2026-10-13（待主理人裁定）**：以下几条 spectral **能等价表达**，
  建议迁回以消除双维护——已列入T-010 交付说明的迁移清单，
  在主理人裁定前**保持现状不动**（动了会破坏 CI 现状）：
  - `test_every_operation_declares_security` ≡ `linkai-security-defined`
  - `test_operations_have_summary` ≡ `linkai-operation-summary-required`
  - `test_error_envelope_schema_is_wellformed` ≈ `linkai-error-envelope-shape`
  - `test_write_operations_declare_error_responses` ≡ `linkai-error-response-4xx`
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import OPENAPI_DIR

pytestmark = pytest.mark.arch_guard

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
#: 租户标识的三种写法 + 契约里 $ref 的公共片段名（common.yaml#/TenantHeader）
_TENANT_MARKERS = {"X-Tenant-Id", "tenantId", "tenant_id", "TenantHeader"}


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


def test_login_paths_agreement_consistency(console_spec) -> None:
    """安全合规铁律：**各登录通道之间**的协议勾选约束必须一致。

    口径说明（主理人 T-016 裁决后调整）：
    早期版本测的是「每条登录路径都必须有协议勾选约束」（存在性检测）。
    那个口径有两个问题：一是把「何约还没补」和「有人删掉了」混为一谈；
    二是若契约将来引入某个天然不需要协议签署的端点（如纯静默续期），
    规则会误报。

    现在的口径是**一致性检测**：找出约束最严的那条登录路径作为基准，
    要求其他登录路径与之对齐。
    - 现状（契约从未定义微信通道的协议约束）：扫码路径与 loginByPhone 不一致 → 报告
    - 何约补齐微信端约束后：全部一致 → 自动转绿
    - 任何人删掉已有约束 → 与基准不一致 → 立即 FAIL

    注意 sms-code（发验证码）与 qrcode/{ticket}（轮询状态）**不是签发令牌的终结点**，
    真正的登录发生在 loginByPhone 与扫码轮询的 confirmed 分支。
    """
    from known_gaps import GAP_WECHAT_LOGIN_MISSING_AGREEMENT

    paths = console_spec.get("paths") or {}
    enforcing: list[str] = []
    not_enforcing: list[str] = []

    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            label = f"{method.upper()} {path} ({op.get('operationId') or '?'})"
            if not _is_agreement_bearing_login(op, path):
                continue
            (enforcing if _enforces_agreement(op) else not_enforcing).append(label)

    # 没有任何路径强制 → 无基准可比，交由 presence 类规则兜底，此处不报
    if not enforcing:
        return

    if not not_enforcing:
        return

    _record_known_gap(GAP_WECHAT_LOGIN_MISSING_AGREEMENT, not_enforcing)
    assert False, (
        "以下登录通道未强制协议勾选，与已强制通道不一致：\n  "
        + "\n  ".join(not_enforcing)
        + "\n已强制协议勾选的通道（基准）：\n  "
        + "\n  ".join(enforcing)
        + "\n\n协议签署是法律效力前提，且微信扫码是默认登录方式。"
          "各登录通道约束不一致即等于可跨通道绕过（契约缺口 GAP-CONTRACT-004）。"
          "需由 Contract Engineer 在契约层补齐微信通道约束。"
          "\n本条当前登记在 known_gaps.py 基线内——补齐后自动转绿。"
    )


def _is_agreement_bearing_login(op: dict[str, Any], path: str) -> bool:
    """是否是一条「签发令牌的登录通道」——协议签署在此有法律意义。

    界定依据是**契约实际语义**（读 v0.1.1 得出，不是猜）：
    - 签发令牌的是两条：POST /auth/phone/login（返回 TokenPair）、
      GET /auth/wechat/qrcode/{ticket}（契约明写「confirmed 时携带令牌」）。
    - 不签发令牌的是：POST /auth/wechat/qrcode（只生成二维码）、
      POST /auth/phone/sms-code（只发验证码）。协议同意不在这里发生，
      把它们纳入会产生假失败。
    - POST /auth/refresh 是续期而非初次登录，协议已在前次登录时同意过，
      排除。

    早期版本我按路径关键词（login/qrcode/sms-code）粗筛，把发验证码和生成二维码
    也算成登录通道了——那是我口径错，会让规则要求在 GET 上传 agreementAccepted。
    这里改为按「是否签发令牌」判定。
    """
    op_id = (op.get("operationId") or "").lower()
    if op_id in {"loginbyphone", "getwechatqrcodeStatus".lower()}:
        return True
    #兜底：契约若新增登录通道，落在 /auth/ 且名字带 login/qrcode 结尾的也纳入
    return path.startswith("/auth/") and op_id.endswith(("login", "qrcodestatus"))


def _enforces_agreement(op: dict[str, Any]) -> bool:
    """该操作是否强制了协议勾选。

    判据（任一成立即算强制）：
    1. 请求体 required 含 agreementAccepted / agreementAcceptedAt 之类字段；
    2. 响应里声明了 403 且描述/错误码含协议相关语义。
    """
    schema = (
        op.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    required = {
        str(x).lower()
        for x in (schema.get("required") or [])
        if isinstance(x, str)
    }
    if any("agreement" in r for r in required):
        return True

    for code, resp in (op.get("responses") or {}).items():
        if str(code) != "403":
            continue
        text = str(resp.get("description", "")).lower()
        if "agreement" in text or "协议" in str(resp.get("description", "")):
            return True
        blob = str(resp).lower()
        if "agreement" in blob:
            return True
    return False


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