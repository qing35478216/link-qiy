"""服务配置：环境变量 → Settings（纯标准库 dataclass，无额外依赖）。

所有项均有本地开发默认值；生产通过环境变量注入（见 .env.example）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

# 本地开发默认 JWT 密钥（生产必须注入 LINKAI_JWT_SECRET；启动时打警告）
DEFAULT_DEV_SECRET = "dev-only-insecure-secret-change-me"  # noqa: S105 - 仅本地开发默认值


@dataclass(frozen=True)
class Settings:
    service_name: str
    port: int
    log_level: str
    database_url: str
    jwt_secret: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    sms_code_ttl_seconds: int
    qr_ttl_seconds: int
    # Mock 微信扫码自动确认延迟（秒）；<=0 不自动确认。仅 Mock Provider 使用。
    wechat_mock_auto_confirm_seconds: float

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.jwt_secret == DEFAULT_DEV_SECRET


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None else float(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "platform"),
        port=_int("PORT", 8000),
        log_level=os.getenv("LOG_LEVEL", "info"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://linkai:linkai_dev_password@localhost:5432/linkai",
        ),
        jwt_secret=os.getenv("LINKAI_JWT_SECRET", "dev-only-insecure-secret-change-me"),
        access_token_ttl_seconds=_int("LINKAI_ACCESS_TOKEN_TTL_SECONDS", 3600),
        refresh_token_ttl_seconds=_int("LINKAI_REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 3600),
        sms_code_ttl_seconds=_int("LINKAI_SMS_CODE_TTL_SECONDS", 300),
        qr_ttl_seconds=300,
        wechat_mock_auto_confirm_seconds=_float("LINKAI_WECHAT_MOCK_AUTO_CONFIRM_SECONDS", 0.0),
    )
