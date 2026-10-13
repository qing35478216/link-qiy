"""短信验证码存储单测：TTL、尝试上限、一次性。"""

from __future__ import annotations

import pytest

from linkai_platform.infra.sms_code_store import MAX_ATTEMPTS, InMemorySmsCodeStore


def test_save_and_verify() -> None:
    store = InMemorySmsCodeStore()
    store.save("13800138000", "123456", ttl_seconds=300)
    assert store.peek_code("13800138000") == "123456"
    assert store.verify("13800138000", "123456") is True
    assert store.peek_code("13800138000") is None  # 成功后清除


def test_wrong_code_counts_attempts() -> None:
    store = InMemorySmsCodeStore()
    store.save("13800138000", "123456", ttl_seconds=300)
    for _ in range(MAX_ATTEMPTS - 1):
        assert store.verify("13800138000", "000000") is False
    assert store.verify("13800138000", "123456") is True  # 最后一次机会仍可用


def test_attempts_exhausted_invalidates() -> None:
    store = InMemorySmsCodeStore()
    store.save("13800138000", "123456", ttl_seconds=300)
    for _ in range(MAX_ATTEMPTS):
        store.verify("13800138000", "000000")
    assert store.verify("13800138000", "123456") is False  # 已达上限，正确码也无效
    assert store.peek_code("13800138000") is None


def test_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    store = InMemorySmsCodeStore()
    store.save("13800138000", "123456", ttl_seconds=10)
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 30)
    assert store.verify("13800138000", "123456") is False


def test_unknown_phone() -> None:
    store = InMemorySmsCodeStore()
    assert store.verify("10000000000", "123456") is False
