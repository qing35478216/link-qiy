"""领域层基础：ID 生成与 UTC 时钟（纯标准库，无框架依赖）。

单独抽出 `utcnow` 便于测试打桩（签到跨日、订单超时关单等时间敏感逻辑）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def date_key(moment: datetime) -> str:
    """UTC 日期键（YYYY-MM-DD）——签到幂等、月度用量聚合的统一口径。

    显式取 UTC：链路各环节（model-proxy 计量、billing 记账）均以 UTC 为准，
    避免服务器时区差异导致"同日重复签到"判定漂移。
    """
    return moment.astimezone(UTC).strftime("%Y-%m-%d")


def month_key(moment: datetime) -> str:
    """UTC 月份键（YYYY-MM）——配额用量聚合周期。"""
    return moment.astimezone(UTC).strftime("%Y-%m")
