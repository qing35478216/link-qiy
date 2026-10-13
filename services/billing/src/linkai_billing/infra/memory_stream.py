"""内存事件流水（dev/测试默认实现；REDIS_URL 未配置时使用）。

语义与 Redis Streams 对齐（同端口同语义，可互换）：
- append 返回自增条目 ID（形态同 Redis 的 ms-seq）；
- read_group 返回**未 ACK** 条目（新消息 + 未决重投）——至少一次语义；
- ack 后不再投递；range_all 返回全部条目（对账全量扫描用）。
"""

from __future__ import annotations

import threading
from collections import defaultdict


class InMemoryMeteringStream:
    """进程内事件流水（单进程部署/测试可用；多实例部署必须用 Redis）。"""

    def __init__(self, *, group: str = "billing") -> None:
        self._lock = threading.Lock()
        self._entries: list[tuple[str, dict[str, str]]] = []
        self._delivered: dict[str, set[str]] = defaultdict(set)  # consumer -> entry_ids
        self._acked: set[str] = set()
        self._group = group
        self._seq = 0

    def append(self, event_id: str, payload: dict[str, str]) -> str:
        with self._lock:
            self._seq += 1
            entry_id = f"{self._seq}-1"
            self._entries.append((entry_id, dict(payload)))
            return entry_id

    def read_group(
        self, *, consumer: str, count: int = 100, block_ms: int = 0
    ) -> list[tuple[str, dict[str, str]]]:
        with self._lock:
            unacked = [
                (eid, payload) for eid, payload in self._entries if eid not in self._acked
            ]
            batch = unacked[:count]
            for eid, _ in batch:
                self._delivered[consumer].add(eid)
            return [(eid, dict(payload)) for eid, payload in batch]

    def ack(self, entry_id: str) -> None:
        with self._lock:
            self._acked.add(entry_id)

    def range_all(self) -> list[tuple[str, dict[str, str]]]:
        with self._lock:
            return [(eid, dict(payload)) for eid, payload in self._entries]

    def pending_ids(self) -> list[str]:
        with self._lock:
            delivered = set().union(*self._delivered.values()) if self._delivered else set()
            return sorted(delivered - self._acked)
