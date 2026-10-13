"""服务配置：环境变量 → Settings（纯标准库 dataclass，无额外依赖）。

资金域相关项（生产必须注入）：
- LINKAI_JWT_SECRET：与 platform 共享（billing 只校验不签发）；
- LINKAI_INTERNAL_TOKEN：服务间内部 API 凭据（metering 消费/plan 同步/对账）；
- LINKAI_PAYMENT_MOCK_SECRET：Mock 支付渠道回调签名密钥；
- REDIS_URL：计量事件流水（Redis Streams）；为空时用内存实现（dev/测试）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# 本地开发默认密钥（生产必须注入；启动时打警告）
DEFAULT_DEV_SECRET = "dev-only-insecure-secret-change-me"  # noqa: S105 - 仅本地开发默认值
DEFAULT_INTERNAL_TOKEN = "dev-only-insecure-internal-token"  # noqa: S105 - 仅本地开发默认值
DEFAULT_PAYMENT_SECRET = "dev-only-insecure-payment-secret"  # noqa: S105 - 仅本地开发默认值


@dataclass(frozen=True)
class Settings:
    service_name: str
    port: int
    log_level: str
    database_url: str
    jwt_secret: str
    internal_token: str
    payment_mock_secret: str
    redis_url: str | None
    # 消费组名（Redis Streams XREADGROUP 的 GROUP 名）
    stream_group: str = "billing"
    stream_key: str = "billing:metering:events"

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.jwt_secret == DEFAULT_DEV_SECRET


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def get_settings() -> Settings:
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "billing"),
        port=_int("PORT", 8010),
        log_level=os.getenv("LOG_LEVEL", "info"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://linkai:linkai_dev_password@localhost:5432/linkai",
        ),
        jwt_secret=os.getenv("LINKAI_JWT_SECRET", DEFAULT_DEV_SECRET),
        internal_token=os.getenv("LINKAI_INTERNAL_TOKEN", DEFAULT_INTERNAL_TOKEN),
        payment_mock_secret=os.getenv("LINKAI_PAYMENT_MOCK_SECRET", DEFAULT_PAYMENT_SECRET),
        redis_url=os.getenv("REDIS_URL") or None,
    )
