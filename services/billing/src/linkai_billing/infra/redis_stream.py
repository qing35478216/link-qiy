"""Redis Streams 实现：计量事件流水（生产路径）。

命令面（与 domain/ports.MeteringEventStream 对应）：
- XADD  {stream} * field value ...   —— model-proxy 产出入流
- XREADGROUP GROUP billing <consumer> STREAMS {stream} >   —— 新消息
- XAUTOCLAIM {stream} billing <consumer> 0 0 COUNT n      —— 未决重投（至少一次）
- XACK  {stream} billing <id>
- XRANGE {stream} - +               —— 对账全量扫描
- XPENDING {stream} billing         —— 未决条目（消费中断痕迹）

读语义（端口契约）：返回本组**未处理**条目 = 新消息 + 未决重投，
至少一次投递；消费侧幂等（request_id 唯一约束）保证重复投递不重复扣减。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redis import Redis
from redis.exceptions import ResponseError


class RedisMeteringStream:
    """基于 redis-py 的事件流水实现（生产；dev/测试用 InMemoryMeteringStream）。"""

    def __init__(self, client: Redis, *, key: str, group: str = "billing") -> None:
        self._client = client
        self._key = key
        self._group = group
        self._ensure_group()

    def _ensure_group(self) -> None:
        """消费组不存在则创建（幂等；BUSYGROUP 忽略）。"""
        try:
            self._client.xgroup_create(self._key, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _decode(fields: Mapping[bytes | str, Any]) -> dict[str, str]:
        return {
            (k.decode() if isinstance(k, bytes) else str(k)): (
                v.decode() if isinstance(v, bytes) else str(v)
            )
            for k, v in fields.items()
        }

    def append(self, event_id: str, payload: dict[str, str]) -> str:
        entry_id = self._client.xadd(self._key, payload)  # type: ignore[arg-type]
        return entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)

    def read_group(
        self, *, consumer: str, count: int = 100, block_ms: int = 0
    ) -> list[tuple[str, dict[str, str]]]:
        entries: list[tuple[str, dict[str, str]]] = []
        seen: set[str] = set()

        def _collect(raw_id: object, fields: Mapping[bytes | str, Any]) -> None:
            key = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
            if key in seen:
                return
            seen.add(key)
            entries.append((key, self._decode(fields)))

        # ① 未决重投（至少一次语义：上次读到没 ACK 的下次重投）
        # redis-py 的 streams 返回结构是运行时形态（list of tuples / dict），
        # 桩类型无法精确表达，显式 Any + 运行时解码（_collect 统一收窄）。
        claimed: Any = None
        try:
            claimed = self._client.xautoclaim(
                self._key, self._group, consumer, min_idle_time=0, start_id="0-0", count=count
            )
        except ResponseError as exc:
            if "NOGROUP" not in str(exc):
                raise
        if claimed:
            # xautoclaim 返回 (next_start_id, messages, deleted_ids)
            for entry_id, fields in claimed[1] or []:
                _collect(entry_id, fields)

        # ② 新消息（> 只取从未投递过的）
        if len(entries) < count:
            response: Any = self._client.xreadgroup(
                self._group, consumer, {self._key: ">"}, count=count - len(entries),
                block=block_ms or None,
            )
            for _stream, messages in response or []:
                for entry_id, fields in messages:
                    _collect(entry_id, fields)
        return entries

    def ack(self, entry_id: str) -> None:
        self._client.xack(self._key, self._group, entry_id)

    def range_all(self) -> list[tuple[str, dict[str, str]]]:
        entries: list[tuple[str, dict[str, str]]] = []
        raw_range: Any = self._client.xrange(self._key)
        for entry_id, fields in raw_range:
            key = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
            entries.append((key, self._decode(fields)))
        return entries

    def pending_ids(self) -> list[str]:
        summary: Any = self._client.xpending_range(
            self._key, self._group, min="-", max="+", count=1000
        )
        ids: list[str] = []
        for item in summary:
            message_id = item["message_id"]
            ids.append(message_id.decode() if isinstance(message_id, bytes) else str(message_id))
        return ids
