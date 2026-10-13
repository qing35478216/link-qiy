"""命令行入口。

    taskmgr register  --id T-002 --kind backend --payload '{"lane":"account"}'
    taskmgr start     --id T-002
    taskmgr checkpoint --id T-002 --step fetch_users --data '{"count":12}'
    taskmgr complete  --id T-002 --result '{"ok":true}'
    taskmgr fail      --id T-002 --error "429 too many requests" [--permanent]
    taskmgr reset     --id T-002
    taskmgr status    --id T-002
    taskmgr list      [--status paused]
    taskmgr recover   [--stale-seconds 120]
    taskmgr run       --id T-002 --handler pkg.mod:handler_fn

DB 路径：--db 指定，或环境变量 TASKMGR_DB，默认 <repo>/.ai-team/runtime/taskmgr.db
（仓库根通过向上查找 .git 定位）。
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from .manager import TaskProcessManager
from .runner import TaskRunner


def _default_db() -> Path:
    here = Path.cwd()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent / ".ai-team" / "runtime" / "taskmgr.db"
    return here / ".ai-team" / "runtime" / "taskmgr.db"


def _load_handler(spec: str):
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise SystemExit(f"--handler 需要 module:attr 形式，得到 {spec!r}")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taskmgr", description="断点续传任务进程管理")
    parser.add_argument("--db", default=None, help="SQLite 进程表路径（默认 .ai-team/runtime/taskmgr.db）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("register")
    p.add_argument("--id", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--payload", default="{}")
    p.add_argument("--max-retries", type=int, default=3)

    p = sub.add_parser("start")
    p.add_argument("--id", required=True)

    p = sub.add_parser("checkpoint")
    p.add_argument("--id", required=True)
    p.add_argument("--step", required=True)
    p.add_argument("--data", default="{}")

    p = sub.add_parser("complete")
    p.add_argument("--id", required=True)
    p.add_argument("--result", default="{}")

    p = sub.add_parser("fail")
    p.add_argument("--id", required=True)
    p.add_argument("--error", required=True)
    p.add_argument("--permanent", action="store_true")

    p = sub.add_parser("reset")
    p.add_argument("--id", required=True)

    p = sub.add_parser("status")
    p.add_argument("--id", required=True)

    p = sub.add_parser("list")
    p.add_argument("--status", default=None)

    p = sub.add_parser("recover")
    p.add_argument("--stale-seconds", type=float, default=120.0)

    p = sub.add_parser("run")
    p.add_argument("--id", required=True)
    p.add_argument("--handler", required=True, help="module:attr")

    args = parser.parse_args(argv)
    mgr = TaskProcessManager(args.db or _default_db())

    if args.cmd == "register":
        rec = mgr.register(args.id, args.kind, json.loads(args.payload), args.max_retries)
        print(json.dumps({"id": rec.id, "status": rec.status.value}, ensure_ascii=False))
    elif args.cmd == "start":
        rec = mgr.start(args.id)
        print(json.dumps({"id": rec.id, "status": rec.status.value}, ensure_ascii=False))
    elif args.cmd == "checkpoint":
        rec = mgr.checkpoint(args.id, args.step, json.loads(args.data))
        print(json.dumps({"id": rec.id, "step": rec.checkpoint.step,
                          "completed": rec.checkpoint.completed_steps}, ensure_ascii=False))
    elif args.cmd == "complete":
        rec = mgr.complete(args.id, json.loads(args.result))
        print(json.dumps({"id": rec.id, "status": rec.status.value}, ensure_ascii=False))
    elif args.cmd == "fail":
        rec = mgr.fail(args.id, args.error, retryable=not args.permanent)
        print(json.dumps({"id": rec.id, "status": rec.status.value,
                          "retry_count": rec.retry_count,
                          "next_retry_at": rec.next_retry_at}, ensure_ascii=False))
    elif args.cmd == "reset":
        rec = mgr.reset(args.id)
        print(json.dumps({"id": rec.id, "status": rec.status.value}, ensure_ascii=False))
    elif args.cmd == "status":
        rec = mgr.get(args.id)
        print(rec.to_json() if rec else json.dumps({"error": "not found"}, ensure_ascii=False))
    elif args.cmd == "list":
        from .models import TaskStatus

        status = TaskStatus(args.status) if args.status else None
        for rec in mgr.list_tasks(status):
            print(json.dumps({"id": rec.id, "kind": rec.kind, "status": rec.status.value,
                              "step": rec.checkpoint.step, "retry_count": rec.retry_count,
                              "last_error": rec.last_error[:80]}, ensure_ascii=False))
    elif args.cmd == "recover":
        for rec in mgr.recover_stale(args.stale_seconds):
            print(json.dumps({"recovered": rec.id, "last_step": rec.checkpoint.step,
                              "completed": len(rec.checkpoint.completed_steps)}, ensure_ascii=False))
    elif args.cmd == "run":
        handler = _load_handler(args.handler)
        rec = TaskRunner(mgr).run(args.id, handler)
        print(json.dumps({"id": rec.id, "status": rec.status.value,
                          "last_error": rec.last_error}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
