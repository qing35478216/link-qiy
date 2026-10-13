"""领域事件与消息总线单测。"""

from __future__ import annotations

from linkai_platform.domain.events import UserCreated
from linkai_platform.infra.bus import InMemoryMessageBus


def test_user_created_event_shape() -> None:
    event = UserCreated(user_id="u1", tenant_id="t1", phone="138****8000")
    assert event.event_type == "UserCreated"
    assert event.payload["user_id"] == "u1"
    assert event.payload["tenant_id"] == "t1"
    assert event.payload["wechat_openid"] is None
    assert event.occurred_at is not None


def test_in_memory_bus_delivers_to_subscribers() -> None:
    bus = InMemoryMessageBus()
    received: list[str] = []
    bus.subscribe(lambda event: received.append(event.event_type))
    bus.publish(UserCreated(user_id="u1", tenant_id="t1"))
    assert received == ["UserCreated"]
    assert len(bus.published) == 1
