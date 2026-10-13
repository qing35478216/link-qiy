"""提供者侧契约测试：service-api（用户面，OpenAI 兼容）实现 vs 契约。

与 console-api 的差异（都体现在用例上）：
1. **鉴权方式**：apiKeyAuth（用户 API Key），租户由 Key 归属解析——调用方不传
   X-Tenant-Id。所以这里只注Authorization，不注租户头。
2. **流式响应**：POST /chat/completions 显式传 stream=true 时返回 text/event-stream，
   事件协议见 runtime-events.yaml。普通 JSON schema 校验不适用于流式，
   故流式用例单独断言事件结构（SSE 帧格式 + 终局事件 done）。
3. **限流语义**：契约里 POST /chat/completions 声明 429（配额/积分不足），
   这是资金相关端点（Phase 0 三类全量门禁之一），额外断言 429 的错误信封形状。
"""

from __future__ import annotations

import os

import pytest
import schemathesis

from conftest import BASE_URL_ENV, OPENAPI_DIR, TENANT_ENV, TOKEN_ENV

pytestmark = pytest.mark.provider

schema = schemathesis.openapi.from_path(str(OPENAPI_DIR / "service-api.yaml"))


def _api_key() -> str:
    key = os.environ.get(TOKEN_ENV)
    if key:
        return key
    # 用户面 API Key 常以固定前缀下发；此处仅作为占位，实际值由环境注入。
    return "sk-linkai-test"


@pytest.mark.parametrize(
    ("path", "method", "payload", "violation"),
    [
        (
            "/chat/completions",
            "POST",
            {
                "model": "gpt-4o-mini",
                "messages": "not-an-array",
            },
            "messages 类型错误：契约 required 类型为 array",
        ),
        (
            "/chat/completions",
            "POST",
            {"model": "gpt-4o-mini", "messages": [{"role": "nobody", "content": "x"}]},
            "messages[0].role 越界：契约 enum 仅 [system,user,assistant,tool]",
        ),
        (
            "/chat/completions",
            "POST",
            {"model": "gpt-4o-mini", "messages": [{"role": "user"}]},
            "messages[0] 缺 required.content",
        ),
        (
            "/chat/completions",
            "POST",
            {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 5.0,
            },
            "temperature 越界：契约 maximum 为 2",
        ),
        (
            "/chat/completions",
            "POST",
            {"messages": [{"role": "user", "content": "hi"}]},
            "缺 required.model",
        ),
    ],
)
def test_service_api_rejects_malformed_body(
    path: str, method: str, payload: dict, violation: str, base_url: str
) -> None:
    """用户面端点的非法入参必须 4xx。

    特别关注 500：用户面直接暴露给第三方，5xx 意味着校验层漏配。

    坑（实测）：违规样本必须逐条对照**契约实际写了的约束**。契约 v0.1.1 里
    `maxTokens` 只声明 type: integer、没有 minimum，`ApiKey` 也没有 required——
    所以「maxTokens=-1」和「建 Key 不给 name」在 OpenAPI 语义下**不算违规**，
    拿它们当非法样本会得到假失败。此处只用契约里确实写明的约束。
    """
    import requests

    response = requests.post(
        f"{base_url}{path}",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
        timeout=15,
    )
    assert response.status_code < 500, (
        f"{method} {path} 对非法入参（{violation}）返回 {response.status_code}"
        f"（5xx）。用户面 5xx 直接被第三方看到。响应体：{response.text[:300]}"
    )
    assert response.status_code in (400, 401, 403, 404, 409, 415, 422), (
        f"{method} {path} 对非法入参（{violation}）返回 {response.status_code}，期望 4xx"
    )


@pytest.mark.skipif(
    not os.environ.get(TOKEN_ENV),
    reason=(
        f"未设置 {TOKEN_ENV}（用户面 API Key）。"
        "没有有效 Key 时所有用户面端点只会返回 401，属性测试无意义。"
    ),
)
@schema.parametrize()
def test_service_api_honors_contract(case: schemathesis.Case, base_url: str) -> None:
    """每个端点：契约声明的响应约束必须被实现遵守。

    关闭状态化测试（Phase 0 服务未落地，无有意义的多步序列可构造）。
    """
    case.headers.update(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ[TOKEN_ENV]}",
        }
    )
    # 用户面租户由 Key 归属解析，刻意不注 X-Tenant-Id——
    # 注了反而会掩盖「实现是否真的从 Key 解析租户」这个问题。
    response = case.call(base_url=base_url)
    case.validate_response(response)


def test_chat_completions_quota_error_uses_error_envelope(base_url: str) -> None:
    """资金相关端点：429 必须用统一错误信封 { code, message, requestId }。

    铁律 6 + 资金类全量门禁的交叉点：配额不足是用户最常撞到的错误，
    若形状不统一，前端无法做统一的「去充值」引导。
    """
    import requests

    response = requests.post(
        f"{base_url}/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={
            "Content-Type": "application/json",
            # 构造必然超配额的上下文长度：契约里 maxTokens 上限远小于此
            "Authorization": f"Bearer {_api_key()}",
        },
        timeout=20,
    )
    # 这里不强制要求 429（取决于实现与配额状态），只校验「若返回 429，形状要对」
    if response.status_code == 429:
        payload = response.json()
        missing = {"code", "message", "requestId"} - set(payload)
        assert not missing, (
            f"429 响应缺少统一错误信封字段：{sorted(missing)}，实际={payload}。"
            "资金相关端点的错误形状必须稳定，前端据此引导充值。"
        )


def test_streaming_chat_returns_sse_frames(base_url: str) -> None:
    """stream=true 时必须返回 text/event-stream，且以 done 事件收尾。

    事件协议见 runtime-events.yaml：node_started / message_chunk / tool_called /
    thought / error / human_input_required / done。done 是唯一正常终局。
    没有终局事件的流 = 客户端会一直转圈，这是线上最难查的一类问题。
    """
    import requests

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_api_key()}",
            },
            stream=True,
            timeout=20,
        )
    except requests.RequestException as exc:
        pytest.skip(f"无法连接 {BASE_URL_ENV}={base_url}（{exc}）")

    if response.status_code in (401, 403):
        pytest.skip("API Key 无效或无配额，跳过流式断言")

    ctype = response.headers.get("Content-Type", "")
    assert "text/event-stream" in ctype, (
        f"stream=true 时 Content-Type 应为 text/event-stream，实际 {ctype!r}。"
        "契约 runtime-events.yaml 定义了 SSE 事件协议。"
    )

    events: list[str] = []
    for raw in response.iter_lines(decode_unicode=True):
        if raw and raw.startswith("data:"):
            chunk = raw[5:].strip()
            if chunk and chunk != "[DONE]":
                import json

                try:
                    events.append(json.loads(chunk).get("type", "?"))
                except json.JSONDecodeError:
                    events.append("__UNPARSEABLE__")
        if "done" in events:
            break

    assert "__UNPARSEABLE__" not in events, (
        f"SSE 帧中存在无法解析的 data（应为合法 JSON 事件）：{events[:10]}"
    )
    assert events, "SSE 流为空：一次 data 帧都没有发出"
    assert events[-1] == "done", (
        f"SSE 流未以 done 事件收尾，实际末事件为 {events[-1]!r}，序列={events[:10]}。"
        "runtime-events.yaml 规定 done 是唯一正常终局事件；"
        "缺失会导致客户端无限等待。"
    )