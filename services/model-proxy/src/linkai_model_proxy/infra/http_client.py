"""出网 HTTP 客户端——**业务侧唯一的厂商调用通道**（铁律 5）。

设计约束：
- 业务/适配器代码**禁止**自行`import httpx`（架构守卫测试强制）；
- 每次请求先过 `SsrfPolicy.validate_url`，不通过直接抛 `ProviderCallError`；
- 不跟随重定向（防重定向绕过 SSRF 校验）；
- 强制超时（防慢速lori 拖垮连接池）；
- 响应体大小上限，防内存打爆；
- 错误分类：429→`ProviderRateLimitedError`，5xx/网络→`ProviderUnavailableError`，
  4xx→`ProviderCallError(retriable=False)`（语义错误，换模型无用）。

厂商实际部署形态分两种（见 infra/adapters/）：
① **ssrf-proxy 模式**（生产）：请求先发给内网 ssrf-proxy，由它出网；
② **直连模式**（本地开发/厂商 SDK 已过校验）：直接连厂商域名，但仍过本地 SSRF 闸门。
两者都走同一份校验逻辑，不存在"绕过闸门"的代码路径。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx

from linkai_model_proxy.domain.errors import (
    ProviderCallError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
    SsrfBlockedError,
)
from linkai_model_proxy.infra.ssrf import SsrfPolicy, SsrfViolation

JsonDict = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderCall:
    """一次厂商 HTTP 调用的描述。"""

    url: str
    payload: JsonDict | None = None
    headers: dict[str, str] | None = None
    method: str = "POST"
    timeout_s: float | None = None

    @staticmethod
    def get(url: str, headers: dict[str, str] | None = None) -> ProviderCall:
        return ProviderCall(url=url, method="GET", headers=headers)


class VendorHttpClient:
    """厂商出网客户端。

    生命周期由 `api/dependencies.py` 管理（应用启动时创建、关闭时释放）。
    """

    def __init__(self, policy: SsrfPolicy, *, client: httpx.AsyncClient | None = None) -> None:
        self._policy = policy
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                policy.connect_timeout_s, read=policy.read_timeout_s, write=policy.read_timeout_s
            ),
            follow_redirects=False,  # 防重定向绕过（ssrf.py 已说明）
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def post_json(self, call: ProviderCall) -> JsonDict:
        """POST JSON 并返回解析后的响应体。"""
        self._guard(call.url)
        try:
            response = await self._client.request(
                call.method,
                call.url,
                json=call.payload,
                headers=call.headers,
                timeout=call.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"厂商请求超时：{exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"厂商网络错误：{exc}") from exc
        return self._parse(response)

    async def stream_sse(self, call: ProviderCall) -> AsyncIterator[JsonDict]:
        """流式请求，逐帧产出 SSE 的 `data:` JSON。

        用 `client.stream()` 保持长连接；调用方**必须**消费完迭代器
        （或调用方负责 `aclose`），否则连接池会被占满。
        """
        self._guard(call.url)
        request = self._client.build_request(
            call.method,
            call.url,
            json=call.payload,
            headers=call.headers,
            timeout=call.timeout_s,
        )
        try:
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(f"厂商流式请求超时：{exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"厂商流式网络错误：{exc}") from exc

        if response.status_code >= 400:
            await response.aclose()
            self._raise_for_status(response, body="")

        return _iter_sse_data(response, self._policy)

    # ---------- 内部 ----------

    def _guard(self, url: str) -> None:
        try:
            self._policy.validate_url(url)
        except SsrfViolation as exc:
            # SSRF 失败是不可重试的安全事件：既不降级也不回显目标细节（避免探测）
            raise SsrfBlockedError(f"出网请求被SSRF 闸门拦截：{exc}") from exc

    def _parse(self, response: httpx.Response) -> JsonDict:
        if response.status_code >= 400:
            self._raise_for_status(response, body=_safe_text(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderCallError(
                f"厂商返回非 JSON 响应（status={response.status_code}）", retriable=False
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderCallError("厂商返回 JSON 顶层不是对象", retriable=False)
        return payload

    def _raise_for_status(self, response: httpx.Response, *, body: str) -> None:
        status = response.status_code
        snippet = body[:300]
        if status == 429:
            raise ProviderRateLimitedError(f"厂商限流（429）：{snippet}")
        if status >= 500:
            raise ProviderUnavailableError(f"厂商服务不可用（{status}）：{snippet}")
        # 4xx：参数/鉴权/配额等语义错误，换模型也解决不了
        raise ProviderCallError(f"厂商拒绝请求（{status}）：{snippet}", retriable=False)


def _safe_text(response: httpx.Response) -> str:
    try:
        return response.text[:300]
    except (UnicodeDecodeError, httpx.HTTPError):  # pragma: no cover - 防御
        return "<unreadable>"


async def _iter_sse_data(response: httpx.Response, policy: SsrfPolicy) -> AsyncIterator[JsonDict]:
    """解析 SSE 流，产出 `data:` 帧里的 JSON 对象。

    遵循 OpenAI 流式约定：
    - `data: [DONE]` 结束流；
    - 其余帧按 JSON 解析，解析失败抛 `ProviderCallError(retriable=False)`。
    """
    try:
        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                break
            if len(raw.encode("utf-8")) > policy.max_response_bytes:
                raise ProviderCallError("厂商单帧超过大小上限", retriable=False)
            try:
                frame = json.loads(raw)
            except ValueError as exc:
                raise ProviderCallError(
                    f"厂商 SSE 帧非法 JSON：{raw[:120]}", retriable=False
                ) from exc
            if isinstance(frame, dict):
                yield frame
    except httpx.TimeoutException as exc:
        raise ProviderUnavailableError(f"厂商流式传输超时：{exc}") from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailableError(f"厂商流式传输中断：{exc}") from exc
    finally:
        await response.aclose()
