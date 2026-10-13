#!/usr/bin/env python3
"""基线快照：记录 QA 守卫的「事实状态」，用于区分「新增缺口」与「文件丢了」。

## 为什么需要这个

本项目发生过一类很难查的故障：worktree 切换 / 分支切换时，未提交的内容丢失，
或文件被另一会话**内容漂移覆盖**。如果只靠「跑测试看绿不绿」，这种情况**察觉不到**——
测试会安静地少跑几个，或者更糟：文件被换成一个空壳，测试从 13 个变成 3 个，
依然是「全绿」。

**判断一个新结果是不是异常，唯一可靠的办法是先有基线。** 没有基线时，
「13 个测试」和「3 个测试」看起来都是绿的。

## 用法

```bash
# 生成基线（干净 worktree 里跑，结果落到baseline.json）
python3 tests/support/snapshot_baseline.py --write

# 对比当前状态与基线，有漂移则退出码 1
python3 tests/support/snapshot_baseline.py --check
```

## 记录什么

只记录**事实**，不记录判断：

| 字段 | 含义 |
|---|---|
| `guards` | 每个守卫用例的 id 与判定结果（PASS / FAIL_EXPECTED / ERROR） |
| `guard_count` | 守卫用例总数 —— 这个数字**缩水**是最强的漂移信号 |
| `gaps` | known_gaps.py 登记的契约缺口编号 |
| `file_fingerprints` | 关键文件的大小与内容哈希 —— 内容被覆盖会立刻暴露 |
| `commit` | 快照对应的 commit，便于日后追溯 |

**刻意不记录覆盖率百分比**：覆盖率会因为用例增删而自然波动，
拿它当基线会制造大量假警报。守卫**数量**与**文件哈希**才是硬信号。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "support" / "baseline.json"

#: 需要指纹追踪的关键文件。少一个就多一个盲区。
TRACKED_FILES = [
    "tests/contracts/known_gaps.py",
    "tests/contracts/test_arch_guards.py",
    "tests/contracts/test_consumer_sdk_drift.py",
    "tests/contracts/test_consumer_openapi_valid.py",
    "tests/contracts/test_provider_console.py",
    "tests/contracts/test_provider_service.py",
    "tests/contracts/conftest.py",
    "tests/gate/gate_chain.py",
    "tests/golden-set/run_golden_set.py",
    "tests/golden-set/schema/golden-case.schema.json",
]


def _run_guards() -> tuple[dict[str, str], list[str]]:
    """执行全部架构守卫，返回 ({用例名: 结果}, 错误列表)。

    刻意**绕开 pytest 进程**：本机内存不足时 pytest 会被 OOM killer 杀，
    而被杀掉的进程可能**返回绿色退出码**（见 test_exit_code.py 的说明）。
    直接调函数能拿到真实的 AssertionError/Exception，且不受进程被杀影响。
    """
    sys.path.insert(0, str(REPO_ROOT / "tests" / "contracts"))
    errors: list[str] = []

    try:
        import yaml

        console = yaml.safe_load(
            (REPO_ROOT / "packages/contracts/openapi/console-api.yaml").read_text("utf-8")
        )
        service = yaml.safe_load(
            (REPO_ROOT / "packages/contracts/openapi/service-api.yaml").read_text("utf-8")
        )
    except Exception as exc:  # pragma: no cover - 环境损坏才会走到
        return {}, [f"无法加载契约：{exc}"]

    try:
        import test_arch_guards as g
    except Exception as exc:
        return {}, [f"无法导入守卫模块：{exc}"]

    class Req:
        def getfixturevalue(self, name: str):
            return {"console_spec": console, "service_spec": service}[name]

    def resolve(attr: str):
        """返回「取到就调用」的函数；守卫不存在时抛 AttributeError。

        坑（实测两处）：
        1. 若在列表字面量里直接写 `g.test_xxx`，函数缺失时构造列表那一刻
           就抛 AttributeError，整个脚本崩溃——而「脚本崩溃」和
           「检测到漂移」的退出码都是 1，调用方无法区分。
        2. 内部函数必须真的接受并转发参数。首版写成 `def run():` 不接受参数，
           配合 `lambda: resolve(...)(a, b)` 就变成「参数传给不接受参数的 run」
           → TypeError，于是全部守卫报 ERROR:TypeError，基线里全是垃圾数据。
        """
        def run(*args, **kwargs):
            fn = getattr(g, attr, None)
            if fn is None:
                raise AttributeError(f"test_arch_guards.{attr} 不存在")
            return fn(*args, **kwargs)
        return run

    # 每项是「守卫名 → 可调用对象」。刻意**不**写成 g.test_xxx 直接引用：
    # 文件被旧版本覆盖时属性缺失会在构造这一行就崩，脚本无法报告漂移。
    # resolve() 把解析推迟到调用时，缺失则抛 AttributeError 并被逐项记录。
    cases: list[tuple[str, object]] = [
        ("security[console]", partial(resolve("test_every_operation_declares_security"), "console_spec", "console-api.yaml", Req())),
        ("security[service]", partial(resolve("test_every_operation_declares_security"), "service_spec", "service-api.yaml", Req())),
        ("tenant_context[console]", partial(resolve("test_console_operations_declare_tenant_context"), "console_spec", "console-api.yaml", Req())),
        ("tenant_context[service_keys]", partial(resolve("test_service_api_keys_bind_tenant"), service)),
        ("public_actually_public", partial(resolve("test_public_operations_are_actually_public"), "console_spec", "console-api.yaml", Req())),
        ("error_envelope_wellformed", resolve("test_error_envelope_schema_is_wellformed")),
        ("operations_have_summary", partial(resolve("test_operations_have_summary"), "console_spec", "console-api.yaml", Req())),
        ("write_ops_declare_4xx", partial(resolve("test_write_operations_declare_error_responses"), console, service)),
        ("error_envelope_referenced", partial(resolve("test_error_envelope_referenced_by_operations"), console, service)),
        ("login_inventory_complete", partial(resolve("test_login_endpoint_inventory_is_complete"), console)),
        ("login_agreement_consistency", partial(resolve("test_login_paths_agreement_consistency"), console)),
        ("no_default_in_error_enums", resolve("test_no_default_keyword_in_error_enums")),
        ("known_gaps_provenance", resolve("test_known_gaps_baseline_has_provenance")),
    ]

    results: dict[str, str] = {}
    for name, fn in cases:
        # 关键：守卫函数本身可能不存在（文件被旧版本覆盖时就会这样）。
        # 那时必须记为 ERROR 继续跑，**绝不能让脚本崩溃**——
        # 崩溃退出码与「检测到漂移」退出码都是 1，调用方分不清，
        # 反而会把「脚本坏了」误当成「检测到漂移」，或反之。
        #
        # 坑（实测）：用 `getattr(g, name, None)` 判断不够——cases 里存的是
        # lambda 闭包，属性缺失早在构造 cases 时就抛 AttributeError 了。
        # 所以必须在构造 cases 时就容忍缺失，这里再逐个兜底。
        try:
            fn()
            results[name] = "PASS"
        except AssertionError:
            # 断言失败：可能是真实回归，也可能是已登记的存量缺口（GAP-CONTRACT-004）。
            # 这里**不做判断**，只记录事实——判断归 Reviewer 与人类。
            results[name] = "FAIL"
        except AttributeError as exc:
            results[name] = "ERROR:MISSING_GUARD"
            errors.append(f"{name} → 守卫函数不存在（文件可能被旧版本覆盖）：{exc}")
        except Exception as exc:
            results[name] = f"ERROR:{type(exc).__name__}"
            errors.append(f"{name} → {type(exc).__name__}: {exc}")
    return results, errors


def _fingerprints() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for rel in TRACKED_FILES:
        p = REPO_ROOT / rel
        if not p.exists():
            out[rel] = {"missing": True}
            continue
        data = p.read_bytes()
        out[rel] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()[:16],
        }
    return out


def _gaps() -> list[str]:
    import re

    text = (REPO_ROOT / "tests" / "contracts" / "known_gaps.py").read_text("utf-8")
    return sorted(set(re.findall(r"GAP-[A-Z]+-\d+", text)))


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout.strip() or "unknown"


def collect() -> dict[str, object]:
    guards, errors = _run_guards()
    return {
        "commit": _commit(),
        "guard_count": len(guards),
        "guards": guards,
        "guard_errors": errors,
        "gaps": _gaps(),
        "file_fingerprints": _fingerprints(),
    }


def _has_commit_touching(rel_path: str, since_commit: str | None) -> bool:
    """该文件自基线 commit 起，是否有 git 提交动过它。

    这是「内容变化」与「内容漂移事故」的分界：
    有提交 = 有人负责的正常改动；无提交 = 工作区被外部改写。

    两种失败都要处理：
    - since_commit 不在当前仓库（浅克隆/换机器）→ 保守返回 True，
      否则 CI 上会误报成事故
    - git 命令失败 → 同上，宁可放过也不误伤
    """
    if not since_commit:
        return True
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", f"{since_commit}..HEAD", "--", rel_path],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if r.returncode != 0:
        return True
    return bool(r.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="QA 守卫基线快照")
    ap.add_argument("--write", action="store_true", help="写入基线文件")
    ap.add_argument("--check", action="store_true", help="与基线对比，有漂移则失败")
    args = ap.parse_args(argv)

    if not (args.write or args.check):
        ap.error("至少指定 --write 或 --check")

    current = collect()

    if args.write:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"✓ 基线已写入 {BASELINE_PATH.relative_to(REPO_ROOT)}")
        print(f"  守卫 {current['guard_count']} 个| 缺口 {len(current['gaps'])} 条 | commit {current['commit']}")
        for name, verdict in current["guards"].items():
            print(f"    {verdict:8s} {name}")
        return 0

    if not BASELINE_PATH.exists():
        print(f"基线不存在：{BASELINE_PATH}\n先跑 --write 建立基线。", file=sys.stderr)
        return 2

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    drift: list[str] = []

    # 1) 守卫数量变化
    b_count, c_count = baseline["guard_count"], current["guard_count"]
    if c_count < b_count:
        drift.append(
            f"守卫数量从 {b_count} 降到 {c_count}（少 {b_count - c_count} 个）。"
            "这通常是文件被覆盖/删除，不是「测试变简单」。"
        )
    elif c_count > b_count:
        # ADVISORY：新增守卫是正常演进，不该让门禁变红。
        # 理由见main() 里的分级说明——常红的门禁等于没有门禁。
        drift.append(f"[ADVISORY] 守卫数量从 {b_count} 增加到 {c_count}（新守卫加入，正常）")

    # 2) 单个守卫结果变化
    b_guards, c_guards = baseline["guards"], current["guards"]
    for name in sorted(set(b_guards) | set(c_guards)):
        bv, cv = b_guards.get(name), c_guards.get(name)
        if bv is None:
            drift.append(f"[ADVISORY] 新增守卫 {name}（基线中不存在，正常）")
        elif cv is None:
            drift.append(f"守卫消失：{name} —— 基线有 {bv}，现在找不到了")
        elif bv != cv:
            drift.append(f"守卫 {name} 结果变化：{bv} → {cv}")

    # 3) 文件指纹变化 —— 关键：内容变了不等于出事了
    #
    # 首版把「文件内容变化」一律判 BLOCKING，这是错的：
    # 任何人**正常改进** tests/ 下的文件，哈希都会变——那会导致
    # 每次改进都红一次。而常红的门禁等于没有门禁。
    #
    # 正确判据是「这个变化有没有对应的 git 提交」：
    #   · 有提交 → 有人负责的正常改动 → ADVISORY
    #   · 无提交 → 工作区被别的东西改了（正是内容漂移事故）→ BLOCKING
    #   · 文件缺失 → 永远BLOCKING（文件丢了不会自己回来）
    b_fp, c_fp = baseline["file_fingerprints"], current["file_fingerprints"]
    baseline_commit = baseline.get("commit")
    for rel in sorted(set(b_fp) | set(c_fp)):
        cur = c_fp.get(rel, {})
        base = b_fp.get(rel, {})
        if cur.get("missing"):
            drift.append(f"文件缺失：{rel}")
        elif not base.get("missing") and base != cur:
            if _has_commit_touching(rel, baseline_commit):
                drift.append(f"[ADVISORY] 文件内容变化：{rel}（有对应提交，正常改动）")
            else:
                drift.append(
                    f"文件内容变化但无对应提交：{rel}。"
                    f"基线 commit={baseline_commit}，"
                    f"但该文件在 git 历史里没有变更记录——"
                    f"高度怀疑是工作区被外部改写（内容漂移事故）。"
                    f"请确认：`git diff {rel}`。若确认无误，跑 --write 刷新基线。"
                )

    # 4) 缺口增减（新增缺口正常，减少是修复）
    b_gaps, c_gaps = set(baseline["gaps"]), set(current["gaps"])
    for g in sorted(c_gaps - b_gaps):
        drift.append(f"[ADVISORY] 新增契约缺口 {g}")
    for g in sorted(b_gaps - c_gaps):
        drift.append(f"契约缺口 {g} 已消失（若确为修复，应在工单留痕）")

    # ── 分级：BLOCKING（红）/ ADVISORY（黄）─────────────────────────
    # 关键设计（主理人指出「这个数字必然变化」的问题）：
    #   **守卫变多、缺口变多都是正常演进，不该让门禁变红。**
    #   若把它们也算 drift，则每次契约修复 / 新增守卫都会红一次——
    #   而常红的门禁等于没有门禁，三个月后大家就学会忽略它。
    #
    #   只有「不该发生的事」才红：
    #     · 守卫数量减少 → 文件被覆盖/删除
    #     · 守卫结果变化 → 回归
    #     · 文件内容变化 → 需确认（可能是覆盖，也可能是正常改动）
    #     · 缺口消失 → 可能被静默删掉
    #   「新增守卫 / 新增缺口 / 守卫数量增加」只提示不拦截。
    blocking = [d for d in drift if not d.startswith("[ADVISORY]")]
    advisory = [d for d in drift if d.startswith("[ADVISORY]")]

    if not drift:
        print("✓ 与基线一致，无漂移")
        print(f"  守卫 {c_count} 个 | 缺口 {len(c_gaps)} 条 | commit {current['commit']}")
        return 0

    if advisory:
        print("提示（不拦截，属正常演进）：")
        for d in advisory:
            print(f"  · {d[len('[ADVISORY] '):]}")
        print("  处置：确认这是有意新增；确认后跑 --write 刷新基线。\n")

    if blocking:
        print("✗ 检测到需要处置的漂移：", file=sys.stderr)
        for d in blocking:
            print(f"  · {d}", file=sys.stderr)
        print(
            "\n处置：先判断这是「回归」还是「文件丢了/被覆盖」。\n"
            "  · 回归 → 修实现\n"
            "  · 文件丢失 → 从 git 恢复（git show <ref>:<path>），不要重写",
            file=sys.stderr,
        )
        return 1

    print("✓ 无阻塞性漂移（仅正常演进），退出码 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())