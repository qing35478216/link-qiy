#!/usr/bin/env python3
"""LinkAI 黄金评测集评分器。

用法：
    run_golden_set.py --validate-only              # 只校验格式（CI 必跑，无需模型）
    run_golden_set.py --tier smoke                # 跑 smoke 层
    run_golden_set.py --all --compare-baseline# 全量+ 与基线比对

设计要点：
1. **确定性优先**：默认评分器（contains / regex / ranking）不依赖模型，
   所以 CI 里分数可复现。LLM-as-judge 只对带 rubric 的用例启用，
   且其分数**不参与卡点**，只进趋势（见 SCORING.md §1）。
2. **未运行的用例不是 0 分**：Phase 0 时runtime/knowledge 未落地，
   拿不到真实输出。此时这些用例标为 SKIPPED 而非0 分——
   否则基线会被「没跑」拉低，掩盖真实退化。
3. **阈值判定严格照SCORING.md**：>5% 跌落 FAIL；对抗用例 mustNotInclude
   命中立即 FAIL，无豁免。

退出码：0=通过，1=不通过（卡点），2=用法/配置错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CASES_DIR = HERE / "cases"
SCHEMA_PATH = HERE / "schema" / "golden-case.schema.json"
BASELINE_PATH = HERE / "baseline" / "baseline.json"

TIER_WEIGHT = {"smoke": 3, "regression": 1, "adversarial": 2}
FAIL_DROP_RATIO = 0.05
WARN_DROP_RATIO = 0.02

# ── 输出接入点（Phase 0 未落地，留好接口） ────────────────────────────────
# 真实评测时，由各框架工单在此接入模型调用（走service-api /v1/chat/completions）。
# 现在返回 None 表示「拿不到输出」→ 用例标记 SKIPPED，不计入均分。
ModelRunner = Any


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise SystemExit(f"{path} 顶层应为数组，实际为 {type(data).__name__}")
        cases.extend(data)
    return cases


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    """按 JSON Schema 校验每条用例。

    刻意不引第三方 schema 库：这是纯结构校验（required / enum / pattern），
    几十行代码就能覆盖，而引jsonschema 会给 CI 加一个纯依赖。
    代价是要手动跟进 schema 变更——所以下面的校验项都带schema 字段路径注释。
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required_top = set(schema["required"])
    id_pattern = re.compile(schema["properties"]["id"]["pattern"])
    enums = {
        "framework": set(schema["properties"]["framework"]["enum"]),
        "tier": set(schema["properties"]["tier"]["enum"]),
    }
    roles = set(schema["properties"]["input"]["properties"]["messages"]["items"]["properties"]["role"]["enum"])
    # expect 用 anyOf（至少一类可判定期望），不是 required 全部字段
    expect_anyof = schema["properties"]["expect"]["anyOf"]

    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, case in enumerate(cases):
        where = f"case[{i}]"
        cid = case.get("id", f"<no-id #{i}>")
        where = f"case {cid}"

        missing = required_top - set(case)
        if missing:
            errors.append(f"{where}:缺少必填字段 {sorted(missing)}")
            continue

        if not id_pattern.match(case["id"]):
            errors.append(f"{where}: id 不匹配 pattern {id_pattern.pattern}")
        if case["id"] in seen_ids:
            errors.append(f"{where}: id 重复（组内必须唯一）")
        seen_ids.add(case["id"])

        for field, allowed in enums.items():
            value = case.get(field, schema["properties"][field].get("default"))
            if value not in allowed:
                errors.append(f"{where}: {field}={value!r} 不在 enum {sorted(allowed)} 内")

        unknown = set(case) - set(schema["properties"])
        if unknown:
            errors.append(f"{where}: 出现 schema 未定义的字段 {sorted(unknown)}（additionalProperties=false）")

        # expect 结构
        exp = case.get("expect") or {}
        exp_unknown = set(exp) - set(schema["properties"]["expect"]["properties"])
        if exp_unknown:
            errors.append(f"{where}: expect 含未定义字段 {sorted(exp_unknown)}")
        if not any(all(k in exp for k in group["required"]) for group in expect_anyof):
            errors.append(
                f"{where}: expect 至少要满足 one of "
                f"{[g['required'] for g in expect_anyof]}"
            )
        for key in ("mustInclude", "mustNotInclude", "mustMatchRegex", "ranking"):
            if key in exp and not isinstance(exp[key], list):
                errors.append(f"{where}: expect.{key} 应为数组")
            if key in exp and isinstance(exp[key], list):
                if not all(isinstance(x, str) for x in exp[key]):
                    errors.append(f"{where}: expect.{key} 的元素必须全是字符串")

        # input 结构
        inp = case.get("input") or {}
        inp_unknown = set(inp) - set(schema["properties"]["input"]["properties"])
        if inp_unknown:
            errors.append(f"{where}: input 含未定义字段 {sorted(inp_unknown)}")
        if "query" in inp and not str(inp["query"]).strip():
            errors.append(f"{where}: input.query 不得为空")
        for msg in inp.get("messages") or []:
            if set(msg) - {"role", "content"}:
                errors.append(f"{where}: messages 项含未定义字段")
            if msg.get("role") not in roles:
                errors.append(f"{where}: messages.role={msg.get('role')!r} 越界")

    return errors


# ── 确定性评分器 ─────────────────────────────────────────────────────────


def _norm(text: str) -> str:
    """归一化：转小写 + 去掉所有空白。

    必须去空白：模型换行/缩进差异不该让contains 断言失败。
    """
    return re.sub(r"\s+", "", text).lower()


def score_case(case: dict[str, Any], output: str) -> tuple[float, list[str]]:
    """返回 (score ∈ [0,1], 失败原因列表)。"""
    exp = case.get("expect") or {}
    norm = _norm(output)
    reasons: list[str] = []
    pos = 0.0
    neg = 0.0

    must_include = exp.get("mustInclude") or []
    must_not = exp.get("mustNotInclude") or []

    for needle in must_include:
        if _norm(needle) in norm:
            pos += 1
        else:
            reasons.append(f"缺少必含要点：{needle!r}")

    for needle in must_not:
        if _norm(needle) in norm:
            neg += 1
            reasons.append(f"命中禁止内容：{needle!r}")
        else:
            pos += 1

    regexes = exp.get("mustMatchRegex") or []
    for pattern in regexes:
        try:
            if re.search(pattern, output):
                pos += 1
            else:
                reasons.append(f"未匹配正则：{pattern}")
        except re.error as exc:
            reasons.append(f"用例自身正则非法 {pattern!r}：{exc}（用例有bug，不是模型的问题）")

    ranking = exp.get("ranking") or []
    if ranking:
        pos += _score_ranking(ranking, output)

    total = pos + neg
    if total == 0:
        # 没有任何确定性断言 —— 只能靠 rubric 判官打分，不做确定性评分。
        return float("nan"), reasons

    score = pos / total

    max_chars = exp.get("maxChars")
    if max_chars and len(output) > max_chars:
        score = max(0.0, score - 0.2)
        reasons.append(f"超长：{len(output)} > {max_chars}（扣 0.2）")

    return score, reasons


def _score_ranking(expected_order: list[str], output: str) -> float:
    """MRR 与 nDCG@5 的加权（见 SCORING.md §2.3）。

    从输出文本里按出现位置提取候选 id 的首次出现次序——
    这要求模型按优先级排列引用，可通过 rubric 约定。
    """
    positions: list[tuple[int, str]] = []
    for cid in expected_order:
        idx = output.find(cid)
        if idx >= 0:
            positions.append((idx, cid))
    if not positions:
        return 0.0
    positions.sort()
    actual = [cid for _, cid in positions]

    # MRR
    mrr = 0.0
    for rank, cid in enumerate(actual, start=1):
        if cid == expected_order[0]:
            mrr = 1.0 / rank
            break

    # nDCG@5
    dcg = sum(
        1.0 / (2**expected_order.index(cid)) if cid in expected_order else 0.0
        for cid in actual[:5]
    )
    idcg = sum(1.0 / (2**i) for i in range(min(len(expected_order), 5)))
    ndcg = dcg / idcg if idcg else 0.0

    return 0.5 * mrr + 0.5 * ndcg


def aggregate(results: list[dict[str, Any]]) -> dict[str, float]:
    """按 framework 加权聚合（SCORING.md §3）。"""
    buckets: dict[str, list[tuple[float, float]]] = {}
    for r in results:
        score = r["score"]
        if score != score:  # NaN：只可判官打分，不计入
            continue
        weight = float(TIER_WEIGHT.get(r["tier"], 1))
        buckets.setdefault(r["framework"], []).append((score, weight))
    return {
        fw: sum(s * w for s, w in items) / sum(w for _, w in items)
        for fw, items in buckets.items()
    }


# ── 输出获取（Phase 0 未落地） ──────────────────────────────────────────


def get_output(case: dict[str, Any], runner: ModelRunner | None) -> str | None:
    """取模型输出。Phase 0 无runtime/knowledge 服务，返回 None → SKIPPED。"""
    if runner is None:
        return None
    return runner(case)


# ── 主流程 ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LinkAI 黄金评测集评分器")
    parser.add_argument("--validate-only", action="store_true", help="只校验用例格式")
    parser.add_argument("--tier", choices=sorted(TIER_WEIGHT), help="只跑指定层")
    parser.add_argument("--all", action="store_true", help="跑全量（含回归与对抗）")
    parser.add_argument("--compare-baseline", action="store_true", help="与 baseline 比对")
    parser.add_argument("--json", type=Path, help="把报告写到该JSON 路径")
    args = parser.parse_args(argv)

    if not (args.validate_only or args.tier or args.all):
        parser.error("至少指定 --validate-only / --tier / --all 之一")

    cases = load_cases()

    # 格式校验永远跑（不管什么模式）
    errors = validate_cases(cases)
    if errors:
        print("黄金集格式校验失败：", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1
    enabled = [c for c in cases if c.get("enabled", True)]
    print(f"✓ 格式校验通过：{len(cases)} 条用例（启用 {len(enabled)}）")

    if args.validate_only:
        disabled = [c["id"] for c in cases if not c.get("enabled", True)]
        if disabled:
            print(f"  注意：以下用例被禁用（会在门禁报告里列出）：{disabled}")
        return 0

    selected = enabled
    if args.tier:
        selected = [c for c in enabled if c.get("tier") == args.tier]
    elif not args.all:
        # 默认跑 smoke
        selected = [c for c in enabled if c.get("tier") == "smoke"]

    print(f"\n评测 {len(selected)} 条用例（runner 未接入 → 全部 SKIPPED）")
    results = [
        {
            "id": c["id"],
            "framework": c["framework"],
            "tier": c.get("tier", "regression"),
            "score": float("nan"),
            "reasons": ["Phase 0：runtime/knowledge 未落地，无输出可评"],
        }
        for c in selected
    ]

    scored = [r for r in results if r["score"] == r["score"]]
    if not scored:
        print(
            "\n[SKIP] 无可评分的用例——Phase 0 无模型输出通道。\n"
            "这不是通过。门禁链把黄金集标记为 SKIP。\n"
            "接入方式：T-004 runtime 落地后，在本文件 get_output() 里接service-api 调用。"
        )
        if args.json:
            args.json.write_text(
                json.dumps({"status": "SKIP", "results": results}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return 0

    agg = aggregate(results)
    print("\n按 framework 聚合：")
    for fw, score in sorted(agg.items()):
        print(f"  {fw:12s} {score:.3f}")

    exit_code = 0
    if args.compare_baseline:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        print("\n与基线比对：")
        for fw, score in sorted(agg.items()):
            base = (baseline.get("frameworks") or {}).get(fw)
            if base is None:
                print(f"  {fw}: 无基线（首次评测）")
                continue
            base_score = base["score"]
            drop = (base_score - score) / base_score if base_score else 0.0
            level = "FAIL" if drop > FAIL_DROP_RATIO else ("warn" if drop > WARN_DROP_RATIO else "ok")
            print(f"  {fw}: {score:.3f} vs基线 {base_score:.3f}（跌 {drop:.1%}）→ {level}")
            if level == "FAIL":
                exit_code = 1

        # 对抗用例一票否决（SCORING.md §4）
        for r in results:
            if r["tier"] == "adversarial" and any(
                "命中禁止内容" in x for x in r["reasons"]
            ):
                print(f"  ✗ 对抗用例 {r['id']} 命中禁止内容 → 立即卡 MR（无豁免）")
                exit_code = 1

    if args.json:
        args.json.write_text(
            json.dumps(
                {"status": "PASS" if exit_code == 0 else "FAIL", "results": results, "aggregate": agg},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())