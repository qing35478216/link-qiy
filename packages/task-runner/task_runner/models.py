"""状态机与记录模型。

状态迁移（单向推进，除恢复类回退外）：

    PENDING ──start()──▶ RUNNING ──complete()──▶ SUCCEEDED
       │                   │  │
       │                   │  └─fail(permanent)──▶ FAILED
       │                   │
       │              recover_stale()          fail(transient)且有剩余次数
       │                   ▼                          ▼
       └─────────────▶ PAUSED ◀──interrupt──  RETRY_WAIT ──次数耗尽──▶ DEAD

约定：
- RUNNING 是"易失态"——进程消失后永远留在 RUNNING，靠 heartbeat 判定中断；
- PAUSED 是"已确认中断、等待恢复"；RETRY_WAIT 是"网络类失败、退避中"；
- DEAD 是重试耗尽，必须人工介入（或人工 reset 后重新 register）。
"""

from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass, field
from typing import Any


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"

    @property
    def terminal(self) -> bool:
        return self in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.DEAD)

    @property
    def resumable(self) -> bool:
        """可恢复/可启动的状态。"""
        return self in (TaskStatus.PENDING, TaskStatus.PAUSED, TaskStatus.RETRY_WAIT)


@dataclass
class Checkpoint:
    """任务进度检查点——断点续传的最小持久单元。"""

    step: str = ""                              # 最近完成的关键节点名
    data: dict[str, Any] = field(default_factory=dict)   # 已完成数据（续跑时可用）
    completed_steps: list[str] = field(default_factory=list)  # 幂等依据
    updated_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "step": self.step,
                "data": self.data,
                "completed_steps": self.completed_steps,
                "updated_at": self.updated_at,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | None) -> "Checkpoint":
        if not raw:
            return cls()
        obj = json.loads(raw)
        return cls(
            step=obj.get("step", ""),
            data=obj.get("data", {}) or {},
            completed_steps=obj.get("completed_steps", []) or [],
            updated_at=obj.get("updated_at", 0.0) or 0.0,
        )


@dataclass
class TaskRecord:
    """进程表中的一行。"""

    id: str
    kind: str
    status: TaskStatus
    payload: dict[str, Any] = field(default_factory=dict)
    checkpoint: Checkpoint = field(default_factory=Checkpoint)
    retry_count: int = 0
    max_retries: int = 3
    last_error: str = ""
    next_retry_at: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    heartbeat_at: float = 0.0

    def to_json(self) -> str:
        return json.dumps(
            {
                "id": self.id,
                "kind": self.kind,
                "status": self.status.value,
                "payload": self.payload,
                "checkpoint": self.checkpoint.to_json(),
                "retry_count": self.retry_count,
                "max_retries": self.max_retries,
                "last_error": self.last_error,
                "next_retry_at": self.next_retry_at,
                "result": self.result,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "heartbeat_at": self.heartbeat_at,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_row(cls, row: tuple) -> "TaskRecord":
        # row 顺序与 manager._SELECT 一致
        return cls(
            id=row[0],
            kind=row[1],
            status=TaskStatus(row[2]),
            payload=json.loads(row[3]) if row[3] else {},
            checkpoint=Checkpoint.from_json(row[4]),
            retry_count=row[5],
            max_retries=row[6],
            last_error=row[7] or "",
            next_retry_at=row[8] or 0.0,
            result=json.loads(row[9]) if row[9] else {},
            created_at=row[10],
            updated_at=row[11],
            heartbeat_at=row[12] or 0.0,
        )


def now() -> float:
    return time.time()
