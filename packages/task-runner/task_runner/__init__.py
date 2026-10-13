"""断点续传任务进程管理机制。

设计目标：任务进程因断网 / 休眠 / 进程被杀而中断后，
重启时能从最后一个检查点无缝恢复，不重复、不丢失。

组成：
- models   状态机与记录模型（TaskStatus / Checkpoint / TaskRecord）
- manager  SQLite 进程表（WAL）的存取与状态迁移，全部单事务
- retry    错误分类（瞬时/永久）、指数退避、网络连通性探测
- runner   带重试与探测的任务执行循环 + 幂等 step()
- cli      命令行：register/checkpoint/complete/fail/status/list/recover/run
"""

from .models import Checkpoint, TaskRecord, TaskStatus
from .manager import TaskProcessManager
from .retry import NetworkProbe, backoff_delay, classify_error
from .runner import ResumeContext, TaskRunner

__all__ = [
    "Checkpoint",
    "TaskRecord",
    "TaskStatus",
    "TaskProcessManager",
    "NetworkProbe",
    "backoff_delay",
    "classify_error",
    "ResumeContext",
    "TaskRunner",
]

__version__ = "0.1.0"
