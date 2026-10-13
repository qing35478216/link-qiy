"""错误分类、指数退避与网络连通性探测。

三类错误语义：
- transient  瞬时错误（断网/超时/连接重置/429/5xx/网关抖动）→ 退避重试
- permanent  确定性失败（参数错/4xx 业务拒绝/校验失败）→ 直接 FAILED，不重试
- fatal      编程错误/KeyboardInterrupt 等 → 原样抛出，交外层处理

网络探测：对多个公共端点做 TCP 连接探测（不依赖 HTTP，休眠唤醒后最快判定
"网通了没"）。全部不可用时返回 False，调用方据此延长退避而不是空转烧重试。
"""

from __future__ import annotations

import random
import socket
import time

TRANSIENT_MARKERS = (
    "timeout", "timed out", "timeouterror",
    "connection", "connectionreset", "connectionrefused", "connectionaborted",
    "econnrefused", "econnreset", "etimedout", "enetunreach", "enetdown",
    "eai_again", "temporary failure in name resolution", "dns",
    "network", "unreachable", "reset by peer", "broken pipe",
    "429", "too many requests", "rate limit",
    "502", "503", "504", "bad gateway", "service unavailable", "gateway timeout",
    "temporarily unavailable", "try again", "stream", "empty stream",
    "queue", "overloaded",
)

PERMANENT_MARKERS = (
    "400", "401", "403", "404", "409", "422",
    "bad request", "unauthorized", "forbidden", "not found", "conflict",
    "validation", "invalid", "permission", "agreement_not_accepted",
)

FATAL_EXCEPTIONS = (KeyboardInterrupt, SystemExit, MemoryError)


def classify_error(exc: BaseException) -> str:
    """返回 transient / permanent / fatal。"""
    if isinstance(exc, FATAL_EXCEPTIONS):
        return "fatal"
    text = f"{type(exc).__name__}: {exc}".lower()
    # fatal 优先于 transient：OSError 的子类里也有 KeyboardInterrupt 无关的硬错误
    for marker in TRANSIENT_MARKERS:
        if marker in text:
            return "transient"
    for marker in PERMANENT_MARKERS:
        if marker in text:
            return "permanent"
    # 未分类的异常默认按瞬时处理（宁可多重试一次，也不错过自愈窗口）
    return "transient"


def backoff_delay(attempt: int, base: float = 2.0, cap: float = 300.0, jitter: bool = True) -> float:
    """第 attempt 次重试（从 0 计）前的等待秒数：base * 2^attempt，封顶 cap。"""
    delay = min(base * (2 ** max(attempt, 0)), cap)
    if jitter:
        delay *= random.uniform(0.5, 1.5)
    return delay


class NetworkProbe:
    """TCP 连通性探测（可注入 fake 以便测试）。"""

    DEFAULT_HOSTS = (("223.5.5.5", 443), ("8.8.8.8", 53), ("119.29.29.29", 53))

    def __init__(self, hosts: tuple[tuple[str, int], ...] | None = None, timeout: float = 3.0) -> None:
        self.hosts = hosts or self.DEFAULT_HOSTS
        self.timeout = timeout

    def probe(self) -> bool:
        for host, port in self.hosts:
            try:
                with socket.create_connection((host, port), timeout=self.timeout):
                    return True
            except OSError:
                continue
        return False


def wait_until(target_at: float, probe: NetworkProbe | None = None, tick: float = 5.0) -> None:
    """睡到 target_at（Unix 秒）。期间周期性探测网络；网不通则顺延一个 tick。

    这同时覆盖"休眠唤醒"：进程休眠期间目标时间会提前过去，醒来后
    先探测再继续，不会在网未通时冲出去送死。
    """
    while True:
        remaining = target_at - time.time()
        if remaining <= 0:
            return
        time.sleep(min(tick, remaining))
        if probe is not None and not probe.probe():
            target_at = max(target_at, time.time() + tick)
