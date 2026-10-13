#!/usr/bin/env python3
"""LinkAI 门禁链——分级门禁编排器。

> **注意：仓库里不存在 `test_gate.py`。**
> 若你在搜索门禁入口时看到有人提到 `tests/test_gate.py`、`test_gate.py 薄壳`
> 或「门禁入口」，那是**误传**——该文件在本仓库的 git 全历史中从未存在过。
> 门禁入口就是本文件（`tests/gate/gate_chain.py`）。写在这里是为了省下后来者
> 的一遍考古。

对应 AGENTS.md 工程规范的「Phase 0 轻量门禁」条款与人类五检查点：

    默认合并制：实现者自验（lint/构建/自测跑通）+ 主理人 diff 抽查 即合并；
    全量 QA 独立门禁仅保留三类：资金相关、契约变更、安全相关；
    领域层覆盖率 ≥70% 在 Phase 0 降为建议值，Phase 1 恢复硬门禁。

用法：
    gate_chain.py --base main                # 比对当前分支 vs main
    gate_chain.py --base main --explain      # 附带分级判定的逐条依据
    gate_chain.py --base main --json out.json

输出：分级报告 + PASS/FAIL + 不通过原因。
退出码：0=门禁通过（含 SKIP 项，但会逐条列出），1=门禁不通过，2=配置/用法错误。

## 为什么要有这个脚本

Phase 0 的门禁规则散落在三处：AGENTS.md 的文字、CI yaml 的占位注释、
各人的记忆里。执行时就会出现「这个 PR 该走哪档」的扯皮。
本脚本把规则**变成代码**：变更路径 → 风险类别 → 该跑哪些检查 → 汇总判定。
规则改一处即可，不用改三处。

## 分级规则（三类全量门禁的识别）

| 类别 | 识别依据 | 为什么必须全量 |
|---|---|---|
| 资金相关 | 路径/内容命中 credits/积分/钱包/配额/计费/price/plan/payment/refund/settlement | 资金 PR 是人类五检查点之一，要抽查+双人评审 |
| 契约变更 | `packages/contracts/**` 或 `packages/sdk-*/**` | 契约评审是人类检查点；API 形状影响所有下游 |
| 安全相关 | auth/jwt/token/password/secret/crypto/sandbox/ssrf/daemon/cors/permission/rbac 等 | 安全基线是架构铁律 5 |

其余一律走Phase 0 轻量门禁（实现者自验 + 主理人 diff 抽查）。

**分级只决定「跑什么」，不代替「谁签字」**：即使被判为轻量，
资金/契约/安全三类也必须在报告里显式提示需要人类确认——
脚本不能替人做决定。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── 风险类别识别规则 ─────────────────────────────────────────────────────
# 刻意用「路径前缀 + 关键词」两层：只看关键词会误判（比如前端有个
# `planColor.ts` 只是配色），只看路径会漏（服务里新增 billing 模块时
# 路径没变但内容在动）。

FUNDING_PATH_PATTERNS = [
    r"^services/billing/",
    r"^packages/billing",
    r"(^|/)credits?(/|\.|$)",
    r"(^|/)billing(/|\.|$)",
    r"(^|/)wallet(/|\.|$)",
    r"(^|/)pricing(/|\.|$)",
    r"(^|/)payment(/|\.|$)",
    r"(^|/)settlement(/|\.|$)",
    r"(^|/)quota(/|\.|$)",
]
CONTRACT_PATH_PATTERNS = [
    r"^packages/contracts/",
    r"^packages/sdk-ts/",
    r"^packages/sdk-py/",
    r"(^|/)openapi/",
]
SECURITY_PATH_PATTERNS = [
    r"(^|/)auth(/|\.|_|$)",
    r"(^|/)security(/|\.|_|$)",
    r"(^|/)permission",
    r"(^|/)rbac",
    r"(^|/)middleware",
    r"(^|/)cors",
    r"(^|/)ssrf",
    r"(^|/)sandbox",
    r"(^|/)daemon",
    r"(^|/)plugin-daemon",
]

# 内容级关键词：只在文件是代码/契约（而非纯文档/样式）时参与判定
FUNDING_CONTENT = re.compile(
    r"\b(credits?|积分|钱包|wallet|quota|配额|计费|billing|payment|refund|退款|"
    r"settlement|结算|pricing|价格|套餐|plan_tier|price_)\b",
    re.IGNORECASE,
)
SECURITY_CONTENT = re.compile(
    r"\b(jwt|jwt_secret|password|passwd|api_key|apikey|secret|token_expire|"
    r"encrypt|decrypt|hash_password|bcrypt|argon2|ssrf|sandbox|cors|"
    r"allow_origins|permission|rbac|authorize|daemon_key|"
    # 提示词与注入防线：改提示词可能造成 system prompt 泄漏 / 越狱绕过 /
    # 提示注入，这三类都归安全评审，不归普通效果回归。
    r"system_prompt|systemprompt|prompt_injection|jailbreak|"
    r"ignore_previous|忽略(前面|之前|以上))\b",
    re.IGNORECASE,
)
CONTRACT_CONTENT = re.compile(
    r"(openapi:|swagger:|\$ref:|operationId:|components:\s*$|"
    r"x-public|X-Tenant-Id)",
    re.IGNORECASE,
)

#: 这些扩展名不参与内容级判定：样式/锁文件里的关键词不代表风险
CONTENT_SKIP_EXT = {
    ".css", ".scss", ".less", ".svg", ".png", ".jpg", ".jpeg", ".gif",
    ".woff", ".woff2", ".ttf", ".lock", ".yaml.lock",
}
CONTENT_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".go", ".yaml", ".yml",
    ".json", ".toml", ".sh",
}

SEVERITY_ORDER = {"BLOCKING": 0, "SHOULD-FIX": 1, "NIT": 2}


# ── 变更收集 ────────────────────────────────────────────────────────────


@dataclass
class Change:
    path: str
    status: str  # A / M / D
    added_lines: int = 0
    categories: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)


def git_changed_files(base: str) -> list[tuple[str, str]]:
    """返回 [(status, path)]。优先用 merge-base，保证分支有新提交时才可比。"""
    # 用 merge-base 而不是直接 diff base：分支落后于 base 时（例如 base 已前进），
    # 直接 diff 会把「base 上别人改的东西」也算成本分支的变更，误判风险类别。
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base
    out = subprocess.run(
        ["git", "diff", "--name-status", "-M", ref, "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"git diff 失败：{out.stderr.strip()}\n（base={base!r} 是否存在？）")

    changes: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0][0]
        path = parts[-1]
        changes.append((status, path))
    return changes


def classify(path: str, status: str, body: str) -> tuple[set[str], list[str]]:
    """判定单个文件的变更类别。返回 (categories, reasons)。"""
    categories: set[str] = set()
    reasons: list[str] = []
    ext = Path(path).suffix.lower()

    for label, pats in (
        ("funding", FUNDING_PATH_PATTERNS),
        ("contract", CONTRACT_PATH_PATTERNS),
        ("security", SECURITY_PATH_PATTERNS),
    ):
        for pat in pats:
            if re.search(pat, path):
                categories.add(label)
                reasons.append(f"路径匹配 {label} 规则 /{pat}/")
                break

    # 内容级判定：仅对代码/契约文件，且只看新增行（避免存量旧债触发）
    if ext in CONTENT_EXT and ext not in CONTENT_SKIP_EXT:
        added = "\n".join(
            ln[1:] for ln in body.splitlines() if ln.startswith("+")
        )
        if FUNDING_CONTENT.search(added):
            categories.add("funding")
            reasons.append("新增内容命中资金关键词")
        if SECURITY_CONTENT.search(added):
            categories.add("security")
            reasons.append("新增内容命中安全关键词")
        if CONTRACT_CONTENT.search(added):
            categories.add("contract")
            reasons.append("新增内容含契约结构标记")

    return categories, reasons


def collect_changes(base: str) -> list[Change]:
    raw = git_changed_files(base)
    if not raw:
        return []
    # 一次 git diff 拿正文，避免逐文件调用
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base
    patch = subprocess.run(
        ["git", "diff", "-M", ref, "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout

    bodies: dict[str, str] = {}
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("+++ "):
            current = line[6:].strip()
            if current.startswith("b/"):
                current = current[2:]
            bodies.setdefault(current, "")
        elif current:
            bodies[current] += line + "\n"

    result: list[Change] = []
    for status, path in raw:
        cats, reasons = classify(path, status, bodies.get(path, ""))
        c = Change(path=path, status=status, categories=cats, reasons=reasons)
        # 统计新增行数（用于报告）
        c.added_lines = sum(
            1 for ln in bodies.get(path, "").splitlines() if ln.startswith("+")
        )
        result.append(c)
    return result


# ── 检查项 ──────────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    status: str  # PASS / FAIL / SKIP / N/A
    detail: str = ""
    reason: str = ""  # SKIP 的原因


def run_cmd(name: str, cmd: list[str], cwd: Path | None = None) -> CheckResult:
    """执行命令并归类结果。

    成功时也保留输出（detail）——门禁链需要靠输出判断「是真的跑过了，
    还是只是没报错」。比如黄金集跑分会打印 [SKIP]，退出码是 0，
    但那不是通过；丢掉输出就没法区分这两种情况。
    """
    try:
        p = subprocess.run(
            cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True, timeout=900
        )
    except FileNotFoundError:
        return CheckResult(name, "SKIP", reason=f"命令不存在：{cmd[0]}（未安装或不在 PATH）")
    except subprocess.TimeoutExpired:
        return CheckResult(name, "FAIL", detail="执行超时（>900s）")

    combined = (p.stdout + p.stderr).strip()
    if p.returncode == 0:
        return CheckResult(name, "PASS", detail=combined)
    tail = combined.splitlines()[-25:] if combined else [f"（无输出，退出码 {p.returncode}）"]
    return CheckResult(name, "FAIL", detail="\n".join(tail))


def check_contracts_lint() -> CheckResult:
    """契约 lint。

    没有 node_modules 时必须 SKIP 而不是 FAIL——spectral 找不到二进制时
    退出码非0，但那意思是「工具没装」不是「契约写错了」。
    报 FAIL 会让所有未装依赖的 CI 变红，而真正的契约问题反而被淹没。
    """
    spectral = REPO_ROOT / "packages" / "contracts" / "node_modules" / ".bin" / "spectral"
    if not spectral.exists():
        return CheckResult(
            "契约 lint (spectral)", "SKIP",
            reason="packages/contracts/node_modules 不存在，spectral 未安装。"
                   "这不是通过——契约机检未执行。请先 `pnpm install`。",
        )
    return run_cmd(
        "契约 lint (spectral)",
        ["pnpm", "-C", "packages/contracts", "lint"],
    )


def check_contracts_diff() -> CheckResult:
    """破坏性变更检测。需要 oasdiff（Go 二进制），未装则 SKIP 而非 PASS。

    这里曾踩坑：scripts/diff.sh 在 oasdiff 缺失时退出码是 1，
    直接透传会被当成「检测到破坏性变更」。必须按输出内容区分两种失败。
    """
    r = run_cmd("契约破坏性变更 (oasdiff)", ["bash", "packages/contracts/scripts/diff.sh"])
    combined = r.detail or ""
    if r.status == "FAIL" and ("未找到 oasdiff" in combined or "install.sh" in combined):
        return CheckResult(
            r.name, "SKIP",
            reason="oasdiff 未安装，破坏性变更未检测。**未检测 ≠ 无破坏性变更**——"
                   "契约变更类 PR 必须先装 oasdiff 再评审。"
                   "安装：curl -fsSL https://raw.githubusercontent.com/oasdiff/oasdiff/main/install.sh | sh",
        )
    return r


def check_contract_tests() -> CheckResult:
    venv = REPO_ROOT / "tests" / "contracts" / ".venv" / "bin" / "python"
    if not venv.exists():
        return CheckResult(
            "契约测试（消费者侧 + 架构守卫）", "SKIP",
            reason=f"未找到 {venv}。首次使用请先跑 tests/contracts/README.md 的安装命令。",
        )
    return run_cmd(
        "契约测试（消费者侧 + 架构守卫）",
        [str(venv), "-m", "pytest", REPO_ROOT / "tests" / "contracts",
         "-m", "consumer or arch_guard", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT / "tests" / "contracts",
    )


def check_golden_set_validation() -> CheckResult:
    return run_cmd(
        "黄金集格式校验",
        [sys.executable, str(REPO_ROOT / "tests" / "golden-set" / "run_golden_set.py"),
         "--validate-only"],
    )


def check_golden_set_score() -> CheckResult:
    """黄金集跑分。Phase 0 无模型输出通道 → SKIP，绝不 PASS。

    判据：脚本自身在无输出时打印 "[SKIP] 无可评分的用例" 并 exit 0。
    若把那个 exit 0 当成 PASS，等于宣称「效果没有回归」——而实际是根本没测。
    """
    r = run_cmd(
        "黄金集跑分",
        [sys.executable, str(REPO_ROOT / "tests" / "golden-set" / "run_golden_set.py"),
         "--all", "--compare-baseline"],
    )
    combined = r.detail or ""
    if "无可评分的用例" in combined or "[SKIP]" in combined:
        return CheckResult(
            "黄金集跑分", "SKIP",
            reason="Phase 0 无模型输出通道（runtime/knowledge 未落地），无法产出有意义分数。"
                   "这不是通过——效果类改动落地后必须补跑。",
        )
    return r


def path_in_territory(path: str, patterns: set[str]) -> bool:
    """判断路径是否落在声明的领地内。

    工单里的领地写法有两种：`.ai-team/**`（glob）与 `tests/**`。
    坑（实测）：直接把 `.ai-team/**` 当前缀比对会失败——`**` 不是字面量。
    必须把结尾的 `/**` 规范成目录前缀再比对，并且要处理
    `.ai-team/tickets/T-010.md`（文件在通配目录内）与 `tests`（目录本身）两种情况。
    """
    for raw in patterns:
        pat = raw.strip().rstrip("/")
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif pat in ("**", "*"):
            return True
        elif pat == path or path.startswith(pat + "/"):
            return True
        elif "*" in pat:
            # 支持 tests/*/contracts 这类单星
            import fnmatch

            if fnmatch.fnmatch(path, pat):
                return True
    return False


def check_territory(changes: list[Change]) -> CheckResult:
    """文件领地检查：只允许改工单「文件领地」节指定的目录。

    Phase 0 各工单领地见 .ai-team/tickets/T-0xx.md。未登记的目录一律视为越界——
    宁可误报让人说明，也不要静默放过。
    """
    territories = load_territories()
    if territories is None:
        # 同样是静默放行：领地图解析不出来 = 我们不知道规矩是什么。
        # 早前这里返回 SKIP，等于「不知道规矩」被当成「没有规矩问题」。
        return CheckResult(
            "文件领地", "FAIL",
            detail=(
                "未能从 .ai-team/tickets/*.md 解析出任何工单的领地声明，"
                "因此无法核对本次改动是否越界。\n\n"
                "这是**检查失效**，不是领地合规。判FAIL 的理由：\n"
                "  · 文件领地是唯一能机检的架构铁律（铁律 3）\n"
                "  · 解析失败时若放行，所有越界改动都能通过门禁\n\n"
                "排查：确认 .ai-team/tickets/ 存在且工单含「## 文件领地」节。"
            ),
        )

    current = current_ticket_id()
    owned = territories.get(current) if current else None

    # ── 无法判定工单 = FAIL，不是 SKIP ──────────────────────────────
    # 曾经的 bug：这里返回 SKIP，于是「分支名不含工单号」的分支
    # （如 fix/model-proxy-ssrf-ipv6、merge_request/123、纯 sha）
    # 领地检查直接跳过 → **越界改动静默放行，红变绿**。
    #
    # 危险等级：测试全绿时最危险，而且它绕过的正是铁律 3（文件领地）——
    # 那是唯一能机检的架构铁律。
    #
    # 为什么不能 SKIP：SKIP 的语义是「这条检查不适用于本次改动」。
    # 而「识别不出工单号」不是不适用，是**输入有问题**——
    # 我们根本不知道该拿哪份领地图来比。输入有问题时放行，
    # 等于把「不知道」当成「没问题」。
    #
    # 真正的「不适用」只有一种：改动范围本来就不涉及领地概念
    # （纯文档、纯 .ai-team 内部记录）——那在下面单独处理。
    if owned is None:
        branch = _branch_name()
        detail = (
            f"无法确定当前改动属于哪个工单，因此**无法核对文件领地**。\n"
            f"  分支名：{branch or '<取不到>'}\n"
            f"  已尝试：① 分支名含 T-xxx ② 变更提交的 message 含 [T-xxx]\n"
            f"  工单：{current or '<未识别>'}\n\n"
            "这不是「检查通过」，也不是「不适用」——是**输入有问题**，故判FAIL。\n"
            "处置（三选一）：\n"
            "  a) 分支改名为 feat/T-xxx-简述（推荐，AGENTS.md 分支约定）\n"
            "  b) 提交信息末尾加 [T-xxx]（AGENTS.md 提交信息约定）\n"
            "  c) 若确为领地外改动（如临时分支），请在工单「文件领地」节补登\n\n"
            "背景：早前这里返回 SKIP，导致无工单号分支的越界改动静默放行。\n"
            "文件领地是唯一能机检的架构铁律（铁律 3），放过它等于形同虚设。"
        )
        # 纯 .ai-team/** 或纯文档改动不涉及领地概念 —— 那才是真·不适用
        if all(
            c.path.startswith((".ai-team/", "docs/")) or c.path.endswith(".md")
            for c in changes
        ):
            return CheckResult(
                "文件领地", "SKIP",
                reason="改动仅涉及文档与 .ai-team 内部记录，不涉及代码领地。",
            )
        return CheckResult("文件领地", "FAIL", detail=detail)

    violations = [f"{c.status} {c.path}" for c in changes if not path_in_territory(c.path, owned)]
    if violations:
        return CheckResult(
            "文件领地", "FAIL",
            detail=f"以下改动超出工单 {current} 声明的领地：\n  "
                   + "\n  ".join(violations)
                   + f"\n声明的领地：{sorted(owned)}"
                   + "\n\n处置：确需跨领地改动时，在工单「文件领地」节补登并说明理由，"
                     "或拆分为独立工单。不要默默改——领地重叠会让并行开发互相覆盖。",
        )
    return CheckResult("文件领地", "PASS")


def load_territories() -> dict[str, set[str]] | None:
    """从工单里解析「## 文件领地」节。

    工单写法不统一，Phase 0 实际见到的是「- .ai-team/**, tests/**」这种
    **逗号分隔的一行**（T-010 工单原文），而不是每行一项。
    坑（实测）：只按行取第一个 token 会把 'tests/**' 整个丢掉，
    结果领地检查把 tests 下的所有改动全报成越界。
    所以这里对每个 bullet 再做逗号切分。
    """
    tickets_dir = REPO_ROOT / ".ai-team" / "tickets"
    if not tickets_dir.is_dir():
        return None
    result: dict[str, set[str]] = {}
    for path in sorted(tickets_dir.glob("T-*.md")):
        owned: set[str] = set()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        in_section = False
        for line in lines:
            if line.startswith("## "):
                in_section = "文件领地" in line
                continue
            if not in_section:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            # 跳过表格行与引用行（它们是说明，不是领地声明）
            if stripped.startswith(("|", ">")):
                continue
            if stripped.startswith("- "):
                stripped = stripped[2:]
            if stripped.startswith("#"):
                continue
            # 逗号 / 顿号 / 分号分隔的多个路径
            for part in re.split(r"[,，、;；]", stripped):
                part = part.strip().strip("`").rstrip("/")
                if not part:
                    continue
                # 去掉行尾说明。实测工单里有两种写法：
                #   1) ASCII 注释：tests/**  # QA 测试
                #   2) 中文括号说明：services/platform/src/**（应用域）——**（不是 #）**
                # 漏掉第2 种会让 T-003 等工单的领地带上「（应用域）」尾巴，
                # 路径比对永远匹配不上，等于该工单的领地检查全线失效。
                part = re.split(r"\s*#|\s*[（(]", part)[0].strip()
                if part:
                    owned.add(part)
        if owned:
            result[path.stem] = owned
    return result or None


def _branch_name() -> str:
    """当前分支名（取不到返回空串，不抛）。"""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        ).stdout.strip()
    except OSError:
        return ""


def current_ticket_id() -> str | None:
    """推断当前改动属于哪个工单。

    两个来源，按可靠性排序：

    1. **分支名** —— 本地与 PR ref（`merge_request/123/feat/T-008-gateway`）
       都能拿到，最可靠。
    2. **提交信息** —— 兜底。CI 的 push 事件里分支名是短 sha，
       `re.search(r"T-(\\d+)", "9f2a1b3")` 匹配不到。此时退回查
       变更涉及的提交信息（约定格式 `... [T-010]`）。

    没有兜底的后果是静默失效：识别不到工单 → `owned` 为 None →
    领地检查无法核对。**必须返回 None 而非猜一个**——调用方据此判 FAIL，
    猜错会让越界改动被拿错误的领地图核对，等于没核对。
    """
    branch = _branch_name()
    m = re.search(r"T-(\d+)", branch)
    if m:
        return f"T-{m.group(1)}"
    return _ticket_from_commits()


def _ticket_from_commits(base: str = "main") -> str | None:
    """从变更涉及的提交信息里提取工单号。

    提交信息约定格式见 AGENTS.md 工程规范：`feat/fix/... (scope): 描述 [T-xxx]`。
    多个工单混在一个分支时取第一个——本仓的做法是一分支一工单，
    出现多个说明分支混了工单，那本身就该人工看。
    """
    try:
        merge_base = subprocess.run(
            ["git", "merge-base", base, "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        ref = merge_base.stdout.strip() if merge_base.returncode == 0 else base
        out = subprocess.run(
            ["git", "log", "--format=%s", "-20", f"{ref}..HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    tickets: list[str] = []
    for line in out.stdout.splitlines():
        for hit in re.findall(r"\[T-(\d+)\]", line):
            if hit not in tickets:
                tickets.append(hit)
    return f"T-{tickets[0]}" if tickets else None


def check_coverage_advisory() -> CheckResult:
    """领域层覆盖率——Phase 0 为**建议值**，故只报不卡。

    AGENTS.md 明确：「领域层覆盖率 ≥70% 在 Phase 0 降为建议值，Phase 1 恢复硬门禁」。
    所以这里绝不返回 FAIL：那会绕过甲方指令。
    """
    services = [
        p for p in (REPO_ROOT / "services").glob("*/")
        if (p / "src").is_dir() or (p / "pyproject.toml").exists()
    ]
    if not services:
        return CheckResult(
            "领域层覆盖率 ≥70%", "SKIP",
            reason="Phase 0：服务代码尚未落地（无 services/*/src），覆盖率不可测。"
                   "Phase 1 恢复为硬门禁。",
        )
    return CheckResult(
        "领域层覆盖率 ≥70%", "SKIP",
        reason="[建议值·Phase 0 不卡门禁] 需各服务落地后由对应工单接入 pytest-cov。"
               "当前 services 下无可测服务。Phase 1 升级为硬门禁。",
    )


# ── 门禁编排 ────────────────────────────────────────────────────────────

LIGHT_GATE = [
    ("契约 lint (spectral)", check_contracts_lint),
    ("契约测试（消费者侧 + 架构守卫）", check_contract_tests),
    ("黄金集格式校验", check_golden_set_validation),
]

FULL_GATE_EXTRA = [
    ("契约破坏性变更 (oasdiff)", check_contracts_diff),
    ("黄金集跑分", check_golden_set_score),
]

FULL_GATE_ONLY = {
    "funding": [("文件领地", None)],  # 领地检查由主流程统一跑
    "contract": [],
    "security": [],
}


def build_plan(categories: set[str]) -> tuple[list, list[str], list[str]]:
    """返回 (检查项列表, 全量理由列表, 人类确认提示列表)。"""
    checks = list(LIGHT_GATE)
    reasons: list[str] = []
    human: list[str] = []

    if categories & {"funding", "contract", "security"}:
        checks.extend(FULL_GATE_EXTRA)

    if "funding" in categories:
        reasons.append("命中资金相关变更 → 全量独立门禁（人类检查点：资金 PR 需抽查 + 双人评审）")
        human.append("资金相关改动：需双人评审 + 主理人抽查后方可合并")
    if "contract" in categories:
        reasons.append("命中契约变更 → 全量独立门禁（人类检查点：契约评审）")
        human.append("契约变更：需 Contract Engineer（何约）+ 主理人确认")
    if "security" in categories:
        reasons.append("命中安全相关变更 → 全量独立门禁（安全评审进 DoD）")
        human.append("安全相关改动：需安全评审 + 主理人确认")

    return checks, reasons, human


# ── 报告 ────────────────────────────────────────────────────────────────


def render_report(
    changes: list[Change],
    categories: set[str],
    results: list[CheckResult],
    reasons: list[str],
    human: list[str],
    ticket: str | None,
    explain: bool,
) -> str:
    L: list[str] = []
    bar = "=" * 72

    L.append(bar)
    L.append("LinkAI 门禁链报告")
    L.append(bar)
    L.append(f"分支工单：{ticket or '<未识别（非 feat/T-xxx-* 分支）>'}")
    L.append(f"变更文件：{len(changes)} 个")

    tier = "全量独立门禁" if categories & {"funding", "contract", "security"} else "Phase 0 轻量门禁"
    L.append(f"门禁档位：{tier}")
    L.append("风险类别：" + (", ".join(sorted(categories)) if categories else "无（普通改动）"))

    if reasons:
        L.append("\n分级依据：")
        for r in reasons:
            L.append(f"  · {r}")
    else:
        L.append(
            "\n分级依据：未命中资金/契约/安全三类 → 走 Phase 0 轻量门禁"
            "（实现者自验 + 主理人 diff 抽查即合并）"
        )

    L.append("\n" + "-" * 72)
    L.append("检查项")
    L.append("-" * 72)
    icons = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "N/A": "-"}
    for r in results:
        L.append(f"  {icons.get(r.status, '?')} [{r.status:4s}] {r.name}")
        # PASS 不打印 detail：run_cmd 为判定 SKIP-vs-PASS 会保留输出，
        # 但正常通过时把整段命令输出倒出来只会淹没报告。
        if r.status == "PASS" and r.detail:
            # 只带一句摘要（pytest 的 "31 passed" / 校验器的用例数），
            # 让报告能自证「跑了多少」，但不倒出整段命令输出。
            summary = next(
                (ln.strip() for ln in r.detail.splitlines()
                 if "passed" in ln or "用例" in ln or "no changes" in ln),
                None,
            )
            if summary:
                L.append(f"        {summary}")
        if r.status == "FAIL" and r.detail:
            for line in r.detail.splitlines():
                L.append(f"        {line}")
        if r.status == "SKIP" and r.reason:
            for line in r.reason.splitlines():
                L.append(f"        {line}")

    skipped = [r for r in results if r.status == "SKIP"]
    if skipped:
        L.append(
            f"\n  注意：{len(skipped)} 项为 SKIP。**SKIP 不是 PASS**——"
            "未跑的检查不构成合规证明，评审时须逐条确认。"
        )

    L.append("\n" + "-" * 72)
    L.append("变更明细")
    L.append("-" * 72)
    if not changes:
        L.append("  （无文件变更）")
    for c in sorted(changes, key=lambda x: (-len(x.categories), x.path)):
        cats = f" [{'/'.join(sorted(c.categories))}]" if c.categories else ""
        L.append(f"  {c.status} {c.path}{cats}  (+{c.added_lines})")
        if explain and c.reasons:
            for r in c.reasons:
                L.append(f"        理由：{r}")

    L.append("\n" + "-" * 72)
    L.append("领域层覆盖率")
    L.append("-" * 72)
    L.append(
        "  [建议值] Phase 0 不作为门禁（AGENTS.md：覆盖率 ≥70% 在 Phase 0 降为建议值，"
        "Phase 1 恢复硬门禁）"
    )

    if human:
        L.append("\n" + "-" * 72)
        L.append("需要人类确认（本脚本无权代为决定）")
        L.append("-" * 72)
        for h in human:
            L.append(f"  ⚑ {h}")

    failed = [r for r in results if r.status == "FAIL"]
    L.append("\n" + bar)
    if failed:
        L.append(f"结论：FAIL（{len(failed)} 项不通过）")
        L.append("")
        L.append("不通过原因：")
        for r in failed:
            first = (r.detail or "").splitlines()
            L.append(f"  · {r.name}：{first[0] if first else '（无输出）'}")
        L.append("")
        L.append("处置：BLOCKING 问题须修复后重跑；例外必须人类批准（角色定义铁律）。")
    else:
        L.append("结论：PASS")
        if categories & {"funding", "contract", "security"}:
            L.append("")
            L.append(
                "本档位为全量独立门禁：脚本层面已通过，**但仍需 QA 独立评审 + "
                "对应人类检查点签字**，脚本通过不等于可以合并。"
            )
        else:
            L.append("")
            L.append("本档位为 Phase 0 轻量门禁：实现者自验已跑通，")
            L.append("待主理人 diff 抽查（领地 + 关键文件）后即合并。")
    L.append(bar)
    return "\n".join(L)


# ── main ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="LinkAI 分级门禁链")
    ap.add_argument("--base", default="main", help="对比基线（默认 main）")
    ap.add_argument("--explain", action="store_true", help="输出每个文件的风险判定理由")
    ap.add_argument("--json", type=Path, help="把结构化报告写到该路径")
    args = ap.parse_args(argv)

    changes = collect_changes(args.base)
    if not changes:
        print(f"与 {args.base} 无文件差异，无需门禁。")
        return 0

    categories: set[str] = set()
    for c in changes:
        categories |= c.categories

    checks, reasons, human = build_plan(categories)
    results: list[CheckResult] = []
    for name, fn in checks:
        if fn is None:
            continue
        results.append(fn())

    # 领地检查始终跑（轻量门禁也需要确认没越界）
    results.insert(0, check_territory(changes))

    ticket = current_ticket_id()
    report = render_report(changes, categories, results, reasons, human, ticket, args.explain)
    print(report)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "ticket": ticket,
                    "base": args.base,
                    "tier": "full" if categories & {"funding", "contract", "security"} else "light",
                    "categories": sorted(categories),
                    "verdict": "FAIL" if any(r.status == "FAIL" for r in results) else "PASS",
                    "results": [
                        {"name": r.name, "status": r.status, "detail": r.detail, "reason": r.reason}
                        for r in results
                    ],
                    "changes": [
                        {"path": c.path, "status": c.status,
                         "categories": sorted(c.categories), "reasons": c.reasons}
                        for c in changes
                    ],
                    "humanConfirmations": human,
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())