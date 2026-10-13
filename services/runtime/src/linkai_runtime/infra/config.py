"""服务配置：环境变量 → Settings（纯标准库 dataclass，无额外依赖）。

所有项均有本地开发默认值；生产通过环境变量注入（见 .env.example）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str
    port: int
    log_level: str
    database_url: str
    # model-proxy（下游）：OpenAI 兼容端点。生产经 gateway 内网域名注入。
    model_proxy_base_url: str
    # platform（上游）：应用设定来源。服务间端点未就绪前 Phase 0 用 static 源。
    platform_base_url: str
    # 服务间调用 platform 的令牌（platform 内部端点就绪后启用；None = 不带）
    service_token: str | None
    # 应用设定来源：static（Phase 0 默认，env 注入）| platform（HTTP 拉取）
    app_profile_source: str
    # static 源的应用设定 JSON：{ appCode: { ...platform AppConfigOut 同构... } }
    static_app_profiles_json: str
    # Phase 0 开发用 API Key 种子："key:tenant[:user],key:tenant[:user]"
    # 仅开发/联调；生产由 platform Key 签发体系供给（技术债见 README）
    dev_api_keys: str
    # 配额守卫（Phase 0 内存）：每租户每日 token 上限
    quota_default_daily_tokens: int
    quota_tenant_daily_tokens_json: str
    # 出网超时（秒）：模型流式调用读超时需放宽
    http_timeout_seconds: float
    http_connect_timeout_seconds: float

    @property
    def tenant_daily_tokens(self) -> dict[str, int]:
        return _parse_int_map(self.quota_tenant_daily_tokens_json)

    @property
    def static_app_profiles(self) -> dict[str, dict[str, object]]:
        return _parse_profile_map(self.static_app_profiles_json)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None else float(raw)


def _parse_int_map(raw: str) -> dict[str, int]:
    """解析 "tenant:100000,tenant2:50000" 形态。"""
    out: dict[str, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        tenant, _, value = part.partition(":")
        try:
            out[tenant.strip()] = int(value.strip())
        except ValueError:
            continue
    return out


def _parse_profile_map(raw: str) -> dict[str, dict[str, object]]:
    """解析 static 应用设定 JSON；非法 JSON 返回空（启动打警告，不静默）。"""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(code): config for code, config in data.items() if isinstance(config, dict)}


#: 本地开发默认上游地址（生产经环境变量注入）
DEFAULT_MODEL_PROXY_URL = "http://localhost:8000"
DEFAULT_PLATFORM_URL = "http://localhost:8002"


def get_settings() -> Settings:
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "runtime"),
        port=_int("PORT", 8010),
        log_level=os.getenv("LOG_LEVEL", "info"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://linkai:linkai_dev_password@localhost:5432/linkai",
        ),
        model_proxy_base_url=os.getenv("LINKAI_MODEL_PROXY_URL", DEFAULT_MODEL_PROXY_URL),
        platform_base_url=os.getenv("LINKAI_PLATFORM_URL", DEFAULT_PLATFORM_URL),
        service_token=os.getenv("LINKAI_SERVICE_TOKEN") or None,
        app_profile_source=os.getenv("LINKAI_APP_PROFILE_SOURCE", "static"),
        static_app_profiles_json=os.getenv("LINKAI_STATIC_APP_PROFILES", ""),
        dev_api_keys=os.getenv("LINKAI_DEV_API_KEYS", ""),
        quota_default_daily_tokens=_int("LINKAI_QUOTA_DEFAULT_DAILY_TOKENS", 1_000_000),
        quota_tenant_daily_tokens_json=os.getenv("LINKAI_QUOTA_TENANT_DAILY_TOKENS", ""),
        http_timeout_seconds=_float("LINKAI_HTTP_TIMEOUT_SECONDS", 120.0),
        http_connect_timeout_seconds=_float("LINKAI_HTTP_CONNECT_TIMEOUT_SECONDS", 5.0),
    )
