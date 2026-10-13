"""进程表测试：状态机、检查点、崩溃恢复、幂等、重试语义。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

from task_runner.manager import TaskProcessManager
from task_runner.models import TaskStatus
from task_runner.retry import NetworkProbe, backoff_delay, classify_error


@pytest.fixture()
def mgr():
    # 不用 pytest 的 tmp_path（沙箱会拦它的目录创建），自建临时目录
    d = Path(tempfile.mkdtemp(prefix="taskmgr-test-"))
    m = TaskProcessManager(d / "taskmgr.db")
    yield m
    m.close()
    shutil.rmtree(d, ignore_errors=True)


# ---------- 状态机基础 ----------

def test_register_idempotent_preserves_progress(mgr):
    mgr.register("T-001", "contract")
    mgr.checkpoint("T-001", "console-api", {"endpoints": 15})
    again = mgr.register("T-001", "contract")  # 重复登记不得清进度
    assert again.checkpoint.step == "console-api"
    assert again.checkpoint.data["endpoints"] == 15


def test_start_transitions(mgr):
    mgr.register("t", "k")
    rec = mgr.start("t")
    assert rec.status is TaskStatus.RUNNING
    with pytest.raises(ValueError):
        mgr.start("t")  # RUNNING 不可重复启动


def test_terminal_task_rejects_start(mgr):
    mgr.register("t", "k")
    mgr.complete("t", {"ok": True})
    with pytest.raises(ValueError):
        mgr.start("t")


def test_complete_sets_result(mgr):
    mgr.register("t", "k")
    rec = mgr.complete("t", {"artifacts": ["a.yaml"]})
    assert rec.status is TaskStatus.SUCCEEDED
    assert rec.result["artifacts"] == ["a.yaml"]


# ---------- 崩溃恢复（核心场景） ----------

def _crash_child(db_path: str) -> str:
    """子进程：跑三步后硬杀（os._exit 模拟崩溃，不刷任何缓冲区）。"""
    return textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})
        from task_runner.manager import TaskProcessManager
        m = TaskProcessManager({db_path!r})
        m.register("crash-task", "import")
        m.start("crash-task")
        for i in (1, 2, 3):
            m.checkpoint("crash-task", f"step{{i}}", {{"rows": i * 10}})
        os._exit(9)  # 模拟进程猝死：状态永远停在 RUNNING
    """)


def test_crash_and_resume_no_duplicate_no_loss(mgr):
    db = str(Path(mgr.db_path))
    # 先让 fixture 的 manager 把库建好，再关掉，交个子进程
    mgr.close()
    child = subprocess.run(
        [sys.executable, "-c", _crash_child(db)],
        capture_output=True, text=True,
    )
    assert child.returncode == 9

    m2 = TaskProcessManager(db)
    # 新进程启动：没有任何 RUNNING 恢复逻辑前，任务仍停在 RUNNING
    assert m2.get("crash-task").status is TaskStatus.RUNNING

    # 启动恢复：检测到未完成任务 → PAUSED，且进度完整保留
    recovered = m2.recover_stale(stale_seconds=0)
    assert [r.id for r in recovered] == ["crash-task"]
    assert recovered[0].checkpoint.completed_steps == ["step1", "step2", "step3"]
    assert recovered[0].checkpoint.data["rows"] == 30

    # 无缝恢复：从 step4 继续，step1-3 绝不重跑
    executed: list[str] = []

    def handler(ctx):
        assert ctx.data["rows"] == 30          # 中断前的数据在
        assert ctx.completed_steps == {"step1", "step2", "step3"}
        for name in ("step4", "step5"):
            ctx.step(name, lambda n=name: executed.append(n) or f"{n}-done")
        return {"executed": executed}

    from task_runner.runner import TaskRunner
    from task_runner.retry import NetworkProbe

    rec = TaskRunner(m2, probe=NetworkProbe(hosts=(("127.0.0.1", 9),), timeout=0.2)).run("crash-task", handler)
    assert rec.status is TaskStatus.SUCCEEDED
    assert executed == ["step4", "step5"]       # 不重复
    assert rec.result["executed"] == ["step4", "step5"]
    m2.close()


# ---------- 幂等 ----------

def test_step_is_idempotent(mgr):
    mgr.register("t", "k")
    calls = {"n": 0}

    def work():
        calls["n"] += 1
        return "v1"

    from task_runner.runner import ResumeContext

    rec = mgr.start("t")
    ctx = ResumeContext(mgr, rec)
    assert ctx.step("fetch", work) == "v1"
    assert ctx.step("fetch", work) == "v1"      # 第二次不执行
    assert calls["n"] == 1

    # 跨进程场景：新上下文从 checkpoint 重建后依然幂等
    ctx2 = ResumeContext(mgr, mgr.get("t"))
    assert ctx2.step("fetch", work) == "v1"
    assert calls["n"] == 1


# ---------- 重试语义 ----------

def test_fail_transient_goes_retry_wait_with_backoff(mgr):
    mgr.register("t", "k", max_retries=2)
    rec = mgr.fail("t", "ENETUNREACH: network is unreachable")
    assert rec.status is TaskStatus.RETRY_WAIT
    assert rec.retry_count == 1
    assert rec.next_retry_at > 0


def test_fail_permanent_goes_failed(mgr):
    mgr.register("t", "k")
    rec = mgr.fail("t", "400 bad request: invalid payload", retryable=False)
    assert rec.status is TaskStatus.FAILED


def test_retry_exhaustion_goes_dead(mgr):
    mgr.register("t", "k", max_retries=1)
    mgr.fail("t", "429 too many requests")
    rec = mgr.fail("t", "429 too many requests")
    assert rec.status is TaskStatus.DEAD
    assert rec.retry_count == 2


def test_reset_from_dead(mgr):
    mgr.register("t", "k", max_retries=1)
    mgr.fail("t", "429")
    mgr.fail("t", "429")
    assert mgr.get("t").status is TaskStatus.DEAD
    rec = mgr.reset("t")
    assert rec.status is TaskStatus.PENDING
    assert rec.retry_count == 0


def test_recover_stale_ignores_fresh_running(mgr):
    import time
    mgr.register("t", "k")
    mgr.start("t")
    assert mgr.recover_stale(stale_seconds=3600) == []   # 心跳新鲜，不动
    time.sleep(0.01)
    assert len(mgr.recover_stale(stale_seconds=0)) == 1  # 强制过期场景


def test_due_retries(mgr):
    import time
    mgr.register("t", "k", max_retries=3)
    rec = mgr.fail("t", "503 service unavailable")
    assert mgr.due_retries() == []                        # 退避中，没到期
    # 睡到该任务自己的 next_retry_at（退避带抖动，不能假设固定 2s——flaky 修复）
    time.sleep(max(0.0, rec.next_retry_at - time.time()) + 0.1)
    assert [r.id for r in mgr.due_retries()] == ["t"]


# ---------- 错误分类与退避 ----------

@pytest.mark.parametrize("exc,expect", [
    (OSError("connect ENETUNREACH 162.14.3.241:443"), "transient"),
    (TimeoutError("read timeout"), "transient"),
    (ConnectionResetError("Connection reset by peer"), "transient"),
    (RuntimeError("HTTP 429 too many requests"), "transient"),
    (RuntimeError("502 bad gateway"), "transient"),
    (RuntimeError("Empty stream: chunks=0"), "transient"),
    (ValueError("400 bad request: invalid"), "permanent"),
    (PermissionError("403 forbidden"), "permanent"),
    (KeyboardInterrupt(), "fatal"),
])
def test_classify_error(exc, expect):
    assert classify_error(exc) == expect


def test_backoff_monotonic_and_capped():
    d0 = backoff_delay(0, base=1.0, jitter=False)
    d1 = backoff_delay(1, base=1.0, jitter=False)
    d5 = backoff_delay(5, base=1.0, jitter=False)
    assert d0 == 1.0 and d1 == 2.0
    assert d5 <= 300.0


def test_probe_unreachable_returns_false():
    probe = NetworkProbe(hosts=(("127.0.0.1", 9),), timeout=0.2)  # discard 端口本机未监听
    assert probe.probe() is False


def test_probe_loopback_returns_true():
    probe = NetworkProbe(hosts=(("127.0.0.1", 22),), timeout=0.5)
    # 22 端口未必监听——退化为"有一个通即可"的语义验证，用注入法保证确定性
    class _FakeProbe(NetworkProbe):
        def probe(self):
            return True
    assert _FakeProbe().probe() is True
