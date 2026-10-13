"""cursor 分页纯函数（契约 common.yaml：limit + cursor，响应含 nextCursor）。

方案：keyset 分页（created_at DESC, id DESC 稳定排序）。cursor 为
base64url("<iso8601>|<id>")，不泄露内部结构且抗注入（解析失败即视为无 cursor）。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    id: str


def encode_cursor(created_at: datetime, item_id: str) -> str:
    raw = f"{created_at.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> Cursor | None:
    """解析 cursor；非法输入返回 None（视为从头开始，不抛错）。"""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        ts, _, item_id = raw.partition("|")
        if not item_id:
            return None
        return Cursor(created_at=datetime.fromisoformat(ts), id=item_id)
    except (ValueError, TypeError):
        return None
