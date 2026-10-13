"""提供者侧契约测试：console-api（管理面）实现 vs 契约。

用 schemathesis 以 OpenAPI 为事实源生成属性测试，打真实 HTTP 服务，
自动校验：状态码在契约内声明、内容类型匹配、响应体符合 schema、无 5xx。

**Phase 0 现实**：服务尚未全部落地，故：
- 未设 LINKAI_BASE_URL → 逐条 skip（conftest 已实现），门禁链标记 SKIP 而非 PASS。
- 部分端点需要特定前置态（先登录拿token、先建应用拿 appId），
  属性测试对这类端点只能验证「契约声明的失败分支」而非成功分支。
  成功路径由各服务工单自己的 pytest 覆盖，QA 侧不重复造。

真正要跑成功路径属性测试，需要两样东西，本工单提供接口：
  LINKAI_TEST_TOKEN   —— 已登录的访问令牌
  LINKAI_TEST_TENANT_ID —— 所属租户
缺任一→ 多数端点只会返回 401/422，属性测试会报大量假失败。
所以本文件在缺这两个变量时额外 skip，并说明原因。
"""

from __future__ import annotations

import os

import pytest
import schemathesis

from conftest import (
    BASE_URL_ENV,
    OPENAPI_DIR,
    TENANT_ENV,
    TOKEN_ENV,
    build_auth_headers,
    base_url,
)

pytestmark = [pytest.mark.provider, pytest.mark.arch_guard]

schema = schemathesis.openapi.from_path(str(OPENAPI_DIR / "console-api.yaml"))


def _has_auth_context() -> bool:
    return bool(os.environ.get(TOKEN_ENV)) and bool(os.environ.get(TENANT_ENV))


@pytest.mark.skipif(
    not _has_auth_context(),
    reason=(
        f"缺少 {TOKEN_ENV} / {TENANT_ENV}，属性测试只会打出一屏401/422 假失败。"
        f"console-api 除登录类端点外全部要求 bearerAuth + X-Tenant-Id。"
        "本地取法：先调 POST /auth/phone/login 或 /auth/wechat/qrcode 轮询拿 accessToken，"
        f"再 export {TOKEN_ENV}=<token> {TENANT_ENV}=<tenantId>。"
    ),
)
@schema.parametrize()
def test_console_api_honors_contract(case: schemathesis.Case, base_url: str) -> None:
    """每个端点：契约声明的响应约束必须被实现遵守。

    坑（实测）：`auth_headers` 是 session 级fixture，直接当dict 用会拿到
    FixtureFunctionDefinition 对象（schemathesis 的 parametrize 会把测试函数
    签名里的每个名字都当作 case 的属性来源），报
    "TypeError: 'FixtureFunctionDefinition' object is not iterable"。
    正确写法是用注入的 fixture 实参，或直接调conftest 的函数取值。
    """
    headers = build_auth_headers()
    case.headers.update(headers)
    response = case.call(base_url=base_url)
    case.validate_response(response)


@pytest.mark.parametrize(
    ("path", "method", "payload", "violation"),
    [
        # 逐条对应契约里的 schema 约束。选的都是**任何 OpenAPI 方言下都确定违规**的构造：
        # 缺 required 字段、enum 取值越界、类型不匹配。
        # 不选「多一个未知字段」——没写 additionalProperties: false 时那不算违规。
        (
            "/auth/wechat/qrcode",
            "POST",
            {"scene": "not-in-enum"},
            "scene 越界：契约 enum 仅 [login, bind]",
        ),
        ("/auth/phone/sms-code", "POST", {}, "缺 required.phone"),
        (
            "/auth/phone/login",
            "POST",
            {},
            "缺 required.phone / smsCode / agreementAccepted",
        ),
        ("/auth/phone/login", "POST", {"phone": "13800138000"}, "缺 smsCode 与 agreementAccepted"),
        ("/auth/refresh", "POST", {}, "缺 required.refreshToken"),
    ],
)
def test_public_auth_endpoints_reject_malformed_body(
    path: str, method: str, payload: dict, violation: str, base_url: str
) -> None:
    """登录类端点的非法入参必须被拒（4xx），不能 500，也不能静默接受。

    这是契约测试里价值最高的一类断言：schemathesis 的属性测试会生成大量畸形
    payload，实现层的 Pydantic 校验一旦漏配就会暴露 5xx。

    坑（实测）：**不要用「多一个未知字段」当非法样本**。契约没写
    `additionalProperties: false`，多字段在 OpenAPI 语义上是合法请求，
    实现返回 200 是对的——那种断言会变成假失败。此处一律用
    「缺 required 字段 / enum 越界」，这两种在任何 OpenAPI 方言下都是确定违规。
    """
    import requests

    response = requests.request(
        method,
        f"{base_url}{path}",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    assert response.status_code < 500, (
        f"{method} {path} 对非法入参（{violation}）返回了 {response.status_code}"
        f"（5xx = 服务端未捕获的校验异常）。响应体：{response.text[:300]}"
    )
    assert response.status_code in (400, 401, 403, 404, 409, 415, 422), (
        f"{method} {path} 对非法入参（{violation}）返回 {response.status_code}，"
        "期望 4xx 族（400/401/403/404/409/415/422）——200/204 说明校验被绕过。"
    )


def test_protected_endpoints_require_auth(base_url: str) -> None:
    """安全基线铁律 5：受保护端点无凭证访问必须 401/403，绝不能 200。

    逐条打一遍console-api 的非公开端点，确认没有「忘记加鉴权」的洞。
    这是横向越权最常见的入口，必须机器守住，不能靠人肉看代码。
    """
    import requests

    from conftest import CONTRACT_FILES

    import yaml

    spec = yaml.safe_load((OPENAPI_DIR / "console-api.yaml").read_text(encoding="utf-8"))
    leaks: list[str] = []
    checked = 0
    for path, item in (spec.get("paths") or {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            op = item.get(method) if isinstance(item, dict) else None
            if not isinstance(op, dict):
                continue
            if op.get("x-public") is True or op.get("security") in ([], None):
                continue
            if not op.get("security"):
                continue
            checked += 1
            response = requests.request(
                method,
                _fill_path_params(base_url, path),
                timeout=15,
            )
            if response.status_code < 400:
                leaks.append(
                    f"{method.upper()} {path} -> {response.status_code}（无凭证即可访问）"
                )
    assert checked > 0, "未解析出任何受保护端点，鉴权测试空转"
    assert not leaks, (
        "以下受保护端点在无凭证情况下未拒绝请求：\n  " + "\n  ".join(leaks) + "\n"
        "架构铁律 5（安全基线）：除 x-public 端点外一律要求鉴权。"
    )


#: 路径参数占位值。用合法 UUID 形态，保证打的是「资源不存在」而不是「路径格式非法」。
_PATH_PARAM_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


def _fill_path_params(base_url: str, path: str) -> str:
    """把 /apps/{appId} 这类模板填成可请求的 URL。

    必须做模板替换后拼进 URL：requests 不接受 appId=... 这样的 kwargs
    （实测会抛 TypeError: Session.request() got an unexpected keyword argument）。
    """
    import re

    return re.sub(r"\{[A-Za-z0-9_]+\}", _PATH_PARAM_PLACEHOLDER, f"{base_url}{path}")


def test_base_url_is_reachable(base_url: str) -> None:
    """先确认服务真的起来了。

    否则后续用例会因为连接失败全红，报错信息指向「契约不符」，
    实际是服务没起——误导性极强的假失败，必须显式区分。
    """
    import requests

    try:
        response = requests.get(base_url, timeout=10)
    except requests.RequestException as exc:
        pytest.fail(
            f"无法连接 {base_url}（{exc}）。"
            f"提供者侧契约测试需要服务在 {BASE_URL_ENV} 上运行。"
            "本失败是「服务不可达」，不是「契约不符」——请勿据此判定实现不合规。"
        )
    # 到这里能连通即可（404 也说明服务活着，只是根路径无路由）
    assert response.status_code < 600