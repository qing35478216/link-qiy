"""MessageBus 的内存实现（服务内同步事件；跨服务 MQ 接入后增加 Outbox/MQ 实现）。"""

from __future__ import annotations

from collections.abc import Callable

from linkai_platform.domain.events import DomainEvent, MessageBus

Subscriber = Callable[[DomainEvent], None]


class InMemoryMessageBus(MessageBus):
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self.published: list[DomainEvent] = []  # 测试/排障用：发布历史

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def publish(self, event: DomainEvent) -> None:
        self.published.append(event)
        for subscriber in list(self._subscribers):
            subscriber(event)
