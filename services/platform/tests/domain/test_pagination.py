"""cursor 分页纯函数单测。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from linkai_platform.domain.pagination import decode_cursor, encode_cursor


def test_roundtrip() -> None:
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)
    cursor = encode_cursor(now, "app-1")
    decoded = decode_cursor(cursor)
    assert decoded is not None
    assert decoded.id == "app-1"
    assert decoded.created_at == now


@pytest.mark.parametrize("bad", ["", "!!!not-base64!!!", "eyJvbmx5IjogImpzb24ifQ"])
def test_decode_invalid_returns_none(bad: str) -> None:
    assert decode_cursor(bad) is None


def test_decode_missing_separator() -> None:
    import base64

    raw = base64.urlsafe_b64encode(b"no-separator-here").decode().rstrip("=")
    assert decode_cursor(raw) is None
