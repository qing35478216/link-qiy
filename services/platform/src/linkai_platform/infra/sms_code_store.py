"""SmsCodeStore 的内存实现：TTL + 尝试次数上限（防爆破）。

Phase 0 用进程内存储（单实例可跑全链路）；接入 Redis 后替换为
RedisSmsCodeStore（key 前缀 + TTL，docs/03 3.4 多租户隔离），接口不变。
"""

from __future__ import annotations

from dataclasses import dataclass

from linkai_platform.domain.repositories import SmsCodeStore

MAX_ATTEMPTS = 5


@dataclass
class _Entry:
    code: str
    expires_at_epoch: float
    attempts: int = 0


class InMemorySmsCodeStore(SmsCodeStore):
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def save(self, phone: str, code: str, ttl_seconds: int) -> None:
        import time

        self._entries[phone] = _Entry(code=code, expires_at_epoch=time.time() + ttl_seconds)

    def verify(self, phone: str, code: str) -> bool:
        import time

        entry = self._entries.get(phone)
        if entry is None:
            return False
        now = time.time()
        if now >= entry.expires_at_epoch or entry.attempts >= MAX_ATTEMPTS:
            del self._entries[phone]
            return False
        if entry.code != code:
            entry.attempts += 1
            return False
        del self._entries[phone]  # 成功后清除，防重放
        return True

    def peek_code(self, phone: str) -> str | None:
        """测试/本地联调用：读取当前有效验证码（不改变状态）。生产代码勿用。"""
        entry = self._entries.get(phone)
        return None if entry is None else entry.code
