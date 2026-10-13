"""TaskProcessManager —— SQLite 进程表。

保证：
1. 所有状态迁移单事务（WAL + busy_timeout，多进程/多协程写入不锁死）；
2. checkpoint 是进度唯一事实来源——只有写进 checkpoint 的步骤才算"已完成"；
3. 启动时 recover_stale() 把"消失的 RUNNING"翻成 PAUSED，交由上层恢复；
4. 任何写操作顺带刷新 heartbeat_at，供中断判定使用。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import Checkpoint, TaskRecord, TaskStatus, now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    status         TEXT NOT NULL,
    payload        TEXT NOT NULL DEFAULT '{}',
    checkpoint     TEXT NOT NULL DEFAULT '{}',
    retry_count    INTEGER NOT NULL DEFAULT 0,
    max_retries    INTEGER NOT NULL DEFAULT 3,
    last_error     TEXT NOT NULL DEFAULT '',
    next_retry_at  REAL NOT NULL DEFAULT 0,
    result         TEXT NOT NULL DEFAULT '{}',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    heartbeat_at   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""

_SELECT = """
SELECT id, kind, status, payload, checkpoint, retry_count, max_retries,
       last_error, next_retry_at, result, created_at, updated_at, heartbeat_at
FROM tasks
"""


class TaskProcessManager:
    """进程表管理器。db_path 指向 SQLite 文件（目录自动创建）。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # ---------- 事务 helpers ----------

    def _write(self, sql: str, params: tuple) -> None:
        with self._conn:  # 单事务：要么状态迁移 + 时间戳一起落，要么都不落
            self._conn.execute(sql, params)

    def _touch(self, task_id: str, **fields: Any) -> None:
        """通用状态写入：自动补 updated_at / heartbeat_at。"""
        fields.setdefault("updated_at", now())
        fields.setdefault("heartbeat_at", now())
        cols = ", ".join(f"{k} = ?" for k in fields)
        self._write(
            f"UPDATE tasks SET {cols} WHERE id = ?",
            (*fields.values(), task_id),
        )

    # ---------- 生命周期 ----------

    def register(
        self,
        task_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> TaskRecord:
        """登记任务（幂等：已存在则原样返回，不覆盖历史进度）。"""
        existing = self.get(task_id)
        if existing is not None:
            return existing
        ts = now()
        self._write(
            """
            INSERT INTO tasks (id, kind, status, payload, max_retries,
                               created_at, updated_at, heartbeat_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, kind, TaskStatus.PENDING.value, json.dumps(payload or {}, ensure_ascii=False),
             max_retries, ts, ts, ts),
        )
        return self.get(task_id)  # type: ignore[return-value]

    def start(self, task_id: str) -> TaskRecord:
        """PENDING/PAUSED/RETRY_WAIT → RUNNING。终态任务拒绝启动。"""
        rec = self._require(task_id)
        if rec.status.terminal:
            raise ValueError(f"task {task_id} 已终态({rec.status.value})，不能启动")
        if not rec.status.resumable:
            raise ValueError(f"task {task_id} 状态 {rec.status.value} 不可启动")
        self._touch(task_id, status=TaskStatus.RUNNING.value)
        return self._require(task_id)

    def checkpoint(self, task_id: str, step: str, data: dict[str, Any] | None = None) -> TaskRecord:
        """关键节点进度落库（幂等的依据）。step 已记录过则只刷新数据与时间。"""
        rec = self._require(task_id)
        cp = rec.checkpoint
        cp.step = step
        if data:
            cp.data.update(data)
        if step not in cp.completed_steps:
            cp.completed_steps.append(step)
        cp.updated_at = now()
        self._write(
            "UPDATE tasks SET checkpoint = ?, updated_at = ?, heartbeat_at = ? WHERE id = ?",
            (cp.to_json(), cp.updated_at, cp.updated_at, task_id),
        )
        return self._require(task_id)

    def heartbeat(self, task_id: str) -> None:
        self._touch(task_id)

    def complete(self, task_id: str, result: dict[str, Any] | None = None) -> TaskRecord:
        self._touch(
            task_id,
            status=TaskStatus.SUCCEEDED.value,
            result=json.dumps(result or {}, ensure_ascii=False),
            last_error="",
            next_retry_at=0.0,
        )
        return self._require(task_id)

    def fail(self, task_id: str, error: str, retryable: bool = True) -> TaskRecord:
        """失败迁移：瞬时错误且次数未耗尽 → RETRY_WAIT（含下次重试时刻）；
        否则 → FAILED；次数耗尽 → DEAD（人工介入）。"""
        rec = self._require(task_id)
        attempts = rec.retry_count + 1
        if retryable and attempts <= rec.max_retries:
            delay = _backoff_for(attempts - 1)
            self._touch(
                task_id,
                status=TaskStatus.RETRY_WAIT.value,
                retry_count=attempts,
                last_error=error,
                next_retry_at=now() + delay,
            )
        elif retryable and attempts > rec.max_retries:
            self._touch(
                task_id,
                status=TaskStatus.DEAD.value,
                retry_count=attempts,
                last_error=error,
            )
        else:
            self._touch(
                task_id,
                status=TaskStatus.FAILED.value,
                retry_count=attempts,
                last_error=error,
            )
        return self._require(task_id)

    def reset(self, task_id: str) -> TaskRecord:
        """DEAD/FAILED 人工复位：清空重试计数与错误，回到 PENDING（保留 checkpoint 可续跑）。"""
        self._touch(
            task_id,
            status=TaskStatus.PENDING.value,
            retry_count=0,
            last_error="",
            next_retry_at=0.0,
        )
        return self._require(task_id)

    # ---------- 恢复 ----------

    def recover_stale(self, stale_seconds: float = 120.0) -> list[TaskRecord]:
        """启动时调用：把心跳超期的 RUNNING 翻成 PAUSED 并返回待恢复清单。

        stale_seconds=0 表示"所有 RUNNING 都视为已中断"（测试/确定性场景用）。
        """
        cutoff = now() - stale_seconds
        rows = self._conn.execute(
            f"{_SELECT} WHERE status = ?", (TaskStatus.RUNNING.value,)
        ).fetchall()
        recovered: list[TaskRecord] = []
        for row in rows:
            rec = TaskRecord.from_row(tuple(row))
            if rec.heartbeat_at <= cutoff:
                self._touch(rec.id, status=TaskStatus.PAUSED.value)
                recovered.append(self._require(rec.id))
        return recovered

    def due_retries(self) -> list[TaskRecord]:
        """到点该重试的 RETRY_WAIT 任务。"""
        rows = self._conn.execute(
            f"{_SELECT} WHERE status = ? AND next_retry_at <= ?",
            (TaskStatus.RETRY_WAIT.value, now()),
        ).fetchall()
        return [TaskRecord.from_row(tuple(r)) for r in rows]

    # ---------- 查询 ----------

    def get(self, task_id: str) -> TaskRecord | None:
        row = self._conn.execute(f"{_SELECT} WHERE id = ?", (task_id,)).fetchone()
        return TaskRecord.from_row(tuple(row)) if row else None

    def list_tasks(self, status: TaskStatus | None = None) -> list[TaskRecord]:
        if status is None:
            rows = self._conn.execute(f"{_SELECT} ORDER BY created_at").fetchall()
        else:
            rows = self._conn.execute(
                f"{_SELECT} WHERE status = ? ORDER BY created_at", (status.value,)
            ).fetchall()
        return [TaskRecord.from_row(tuple(r)) for r in rows]

    def _require(self, task_id: str) -> TaskRecord:
        rec = self.get(task_id)
        if rec is None:
            raise KeyError(f"task {task_id} 不存在")
        return rec

    def close(self) -> None:
        self._conn.close()


def _backoff_for(attempt: int) -> float:
    from .retry import backoff_delay

    return backoff_delay(attempt)
