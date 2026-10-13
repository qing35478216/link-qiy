"""TaskRunner —— 带重试、网络探测与断点恢复的执行循环。

handler 契约：
    def handler(ctx: ResumeContext) -> dict:
        # ctx.data           上一个检查点保存的数据
        # ctx.completed_steps 已完成步骤集合
        # ctx.step(name, fn) 幂等步骤：已执行过直接返回缓存结果，不重复跑
        # ctx.save(data)     手动追加检查点数据
        return {"ok": True, ...}   # 返回值作为 complete() 的 result

循环语义：
- start → RUNNING；handler 抛异常 → classify_error：
    transient  且次数未耗尽 → RETRY_WAIT + 退避；到期先 probe，网不通顺延
    permanent  → FAILED（不重试，重试无意义）
    fatal      → 原样抛出（KeyboardInterrupt 等）
- 成功 → complete(result)；次数耗尽 → DEAD
- 每轮开始前若 rec 已是终态则直接返回（不重复执行）
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .manager import TaskProcessManager
from .models import TaskRecord, TaskStatus
from .retry import NetworkProbe, classify_error, wait_until


class ResumeContext:
    """交给 handler 的恢复上下文——断点续传的消费侧。"""

    def __init__(self, manager: TaskProcessManager, record: TaskRecord) -> None:
        self._mgr = manager
        self.task_id = record.id
        self.data: dict[str, Any] = dict(record.checkpoint.data)
        self.completed_steps: set[str] = set(record.checkpoint.completed_steps)
        # 从 checkpoint 重建 step 缓存：跨进程恢复后，已完成步骤直接返回
        # 上次的结果（语义：同一个 step 的返回值在续跑中保持稳定）
        self._step_results: dict[str, Any] = {
            name[len("__step__"):]: value
            for name, value in self.data.items()
            if name.startswith("__step__")
        }

    def step(self, name: str, fn: Callable[[], Any]) -> Any:
        """幂等执行一个步骤。已在 checkpoint 里 → 直接返回缓存值，绝不重复。"""
        if name in self.completed_steps:
            return self._step_results.get(name)
        result = fn()
        self._step_results[name] = result
        self.completed_steps.add(name)
        # 立即落库：此后进程任何时刻死掉，这一步都不重跑
        self._mgr.checkpoint(self.task_id, name, {f"__step__{name}": _jsonable(result)})
        return result

    def save(self, data: dict[str, Any]) -> None:
        """追加业务数据到检查点（如已处理条目数、游标位置）。"""
        self.data.update(data)
        self._mgr.checkpoint(self.task_id, self._mgr.get(self.task_id).checkpoint.step, data)

    @property
    def last_step(self) -> str:
        return self._mgr.get(self.task_id).checkpoint.step if self._mgr.get(self.task_id) else ""


class TaskRunner:
    def __init__(
        self,
        manager: TaskProcessManager,
        probe: NetworkProbe | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.mgr = manager
        self.probe = probe or NetworkProbe()
        self.sleep = sleep

    def run(self, task_id: str, handler: Callable[[ResumeContext], dict]) -> TaskRecord:
        """执行（或恢复执行）一个任务，直到终态。返回最终记录。"""
        rec = self.mgr.get(task_id)
        if rec is None:
            raise KeyError(f"task {task_id} 不存在，先 register")
        if rec.status.terminal:
            return rec

        while True:
            rec = self.mgr.get(task_id)
            if rec.status.terminal:
                return rec

            if rec.status is TaskStatus.RETRY_WAIT:
                # 到点前先探网：休眠唤醒/断网场景，网不通就顺延，不空转
                if rec.next_retry_at > time.time():
                    wait_until(rec.next_retry_at, probe=self.probe, sleep=self.sleep)
                elif not self.probe.probe():
                    self.sleep(30)
                    continue

            self.mgr.start(task_id)
            ctx = ResumeContext(self.mgr, self.mgr.get(task_id))
            try:
                result = handler(ctx)
                return self.mgr.complete(task_id, _jsonable(result))
            except Exception as exc:  # noqa: BLE001 —— 分类后决定去向
                kind = classify_error(exc)
                if kind == "fatal":
                    raise
                rec = self.mgr.fail(task_id, f"{type(exc).__name__}: {exc}", retryable=(kind == "transient"))
                if rec.status is TaskStatus.DEAD:
                    return rec
                # RETRY_WAIT / FAILED：FAILED 下轮循环开头直接返回


def _jsonable(obj: Any) -> Any:
    """把 handler 返回值规整为可 JSON 序列化形态（失败就退化为 repr）。"""
    import json

    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return repr(obj)
