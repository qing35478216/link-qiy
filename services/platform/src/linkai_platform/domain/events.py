"""领域事件与消息总线抽象（docs/03 3.4 横切机制 ③）。

服务内同步事件走 MessageBus；跨服务 MQ 事件（UserCreated → billing 开户等）
由 infra 的实现决定投递方式，Phase 0 为内存实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from linkai_platform.domain.users import utcnow


@dataclass(frozen=True)
class DomainEvent:
    """领域事件基类：携带事件类型名、发生时间与负载。"""

    event_type: str
    occurred_at: datetime = field(default_factory=utcnow)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UserCreated(DomainEvent):
    """用户注册成功（首次登录即注册）。payload: user_id / tenant_id / phone? / openid?。"""

    def __init__(
        self,
        *,
        user_id: str,
        tenant_id: str,
        phone: str | None = None,
        wechat_openid: str | None = None,
    ) -> None:
        object.__setattr__(self, "event_type", "UserCreated")
        object.__setattr__(self, "occurred_at", utcnow())
        object.__setattr__(
            self,
            "payload",
            {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "phone": phone,
                "wechat_openid": wechat_openid,
            },
        )


@dataclass(frozen=True)
class AppPublished(DomainEvent):
    """应用发布到广场（平台内部领域事件；跨服务 MQ 事件 v0.2 契约化后再外发）。

    payload: app_id / tenant_id / version
    """

    def __init__(self, *, app_id: str, tenant_id: str, version: int) -> None:
        object.__setattr__(self, "event_type", "AppPublished")
        object.__setattr__(self, "occurred_at", utcnow())
        object.__setattr__(
            self,
            "payload",
            {"app_id": app_id, "tenant_id": tenant_id, "version": version},
        )


@dataclass(frozen=True)
class AppUnpublished(DomainEvent):
    """应用下架（平台内部领域事件，v0.2 契约化）。payload 同 AppPublished。"""

    def __init__(self, *, app_id: str, tenant_id: str, version: int) -> None:
        object.__setattr__(self, "event_type", "AppUnpublished")
        object.__setattr__(self, "occurred_at", utcnow())
        object.__setattr__(
            self,
            "payload",
            {"app_id": app_id, "tenant_id": tenant_id, "version": version},
        )


class MessageBus(Protocol):
    """领域事件总线抽象。infra 层提供实现（Phase 0 内存；后续接 MQ）。"""

    def publish(self, event: DomainEvent) -> None:
        """发布事件。同步总线要求 publish 返回前所有订阅者已处理。"""
        ...
