"""应用设定提供者（实现 domain.ports.AppProfileProvider 协议）。

两个实现，经 LINKAI_APP_PROFILE_SOURCE 切换：
- StaticAppProfileProvider（Phase 0 默认）：env 注入的应用设定 JSON，
  供联调/演示/测试零依赖跑通出口链路；
- PlatformHttpAppProfileProvider（生产路径）：HTTP 调 platform 读应用配置。
  **依赖 platform 服务间端点**（当前只有 console JWT 端点 → 401，即技术债现象；
  缺陷单：platform 需提供 GET /internal/apps/{appCode}/runtime-profile，
  服务间鉴权走 X-Service-Token）。端点就绪前本实现对 platform 调用必然失败，
  失败即抛 AppConfigUnavailableError（502），不会静默降级到空设定。
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from linkai_runtime.domain.app_profile import AppProfile
from linkai_runtime.domain.errors import AppConfigUnavailableError

#: platform 应用配置端点（console-api：GET /apps/{appId}/config）
_PLATFORM_CONFIG_PATH = "/apps/{app_code}/config"


class StaticAppProfileProvider:
    """静态应用设定（env JSON）。tenant 维度不做隔离（Phase 0 联调用；

    生产必须切 platform 源——应用设定是租户数据，静态源会跨租户串配置）。
    """

    def __init__(self, profiles: Mapping[str, Mapping[str, object]]) -> None:
        self._profiles = {
            code: AppProfile.from_platform_config(app_code=code, config=config)
            for code, config in profiles.items()
        }

    async def get_profile(self, tenant_id: str, app_code: str) -> AppProfile | None:
        return self._profiles.get(app_code)


class PlatformHttpAppProfileProvider:
    """经 HTTP 调 platform 读应用配置（生产路径；端点就绪前按技术债处理）。"""

    def __init__(
        self,
        base_url: str,
        *,
        service_token: str | None = None,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout_seconds
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_profile(self, tenant_id: str, app_code: str) -> AppProfile | None:
        headers = {"X-Tenant-Id": tenant_id}
        if self._service_token:
            headers["Authorization"] = f"Bearer {self._service_token}"
        url = self._base_url + _PLATFORM_CONFIG_PATH.format(app_code=app_code)
        try:
            response = await self._get_client().get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise AppConfigUnavailableError(f"platform 应用配置读取失败：{exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise AppConfigUnavailableError(
                "platform 应用配置服务间鉴权失败（技术债：内部端点/X-Service-Token 未就绪）"
            )
        if response.status_code >= 500:
            raise AppConfigUnavailableError(
                f"platform 应用配置读取 5xx：HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppConfigUnavailableError("platform 应用配置响应非 JSON") from exc
        if not isinstance(payload, dict):
            raise AppConfigUnavailableError("platform 应用配置响应形态非法")
        return AppProfile.from_platform_config(app_code=app_code, config=payload)
