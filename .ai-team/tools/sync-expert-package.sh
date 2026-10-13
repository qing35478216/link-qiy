#!/usr/bin/env bash
# 同步 .ai-team/roles/ 与 WorkBuddy 专家包 linkai-dev-team/agents/ 的"开源优先"条款。
#
# 背景：agent MD 带 WorkBuddy 必需 frontmatter（name/description/displayName/profession/maxTurns），
# 正文由角色文件改写而来。两者不是 1:1 覆盖关系——整文件覆盖会抹掉 frontmatter 导致校验失败。
# 因此本脚本只做正文增量同步：把角色文件里的"开源优先"条款注入 agent MD 正文（已存在则跳过）。
#
# 用法：bash .ai-team/tools/sync-expert-package.sh [--check]
#   --check  只比对不写入（退出码 1 表示有漂移）
# 兼容 bash 3.2（macOS 自带版本）
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROLES_DIR="$REPO_ROOT/.ai-team/roles"
PLUGIN_DIR="${HOME}/.workbuddy/plugins/marketplaces/my-experts/plugins/linkai-dev-team"
CACHE_DIR="${HOME}/.workbuddy/plugins/cache/my-experts/linkai-dev-team/1.0.0"
AGENT_MD_SKILL="/Users/qiy/.workbuddy/plugins/cache/workbuddy-builtin/skill-expert-manager"
VALIDATE="$(ls -d "$AGENT_MD_SKILL"/*/scripts/validate_expert.py 2>/dev/null | tail -1)"

# 角色文件 -> Agent MD 文件名（顺序与 docs/05 的 12 角色一致）
PAIRS="
01-orchestrator.md:linkai-dev-team-team-lead.md
02-contract-engineer.md:contract-engineer.md
03-backend-platform.md:backend-platform.md
04-runtime-engineer.md:runtime-engineer.md
05-ai-framework.md:ai-framework.md
06-workflow-engineer.md:workflow-engineer.md
07-channel-engineer.md:channel-engineer.md
08-frontend-console.md:frontend-console.md
09-canvas-engineer.md:canvas-engineer.md
10-billing-engineer.md:billing-engineer.md
11-marketing-sdk.md:marketing-sdk.md
12-qa-reviewer.md:qa-reviewer.md
devops.md:devops.md
"

# 权威条款文本（取自 AGENTS.md 铁律 8，与角色文件末段一致）
CLAUSE_LINE1="## 开源优先（AGENTS.md 铁律 8）"
CLAUSE_LINE2="通用功能模块动手前先检索 GitHub 成熟开源库；选型核查维护活跃度（近 3 个月有提交或发版）、Issue 响应（open/closed 比、维护者响应速度）、许可证兼容（MIT/Apache-2.0/BSD 可直接引入；GPL/AGPL 必须升级人类确认，SaaS 场景防传染）、技术栈与依赖版本匹配四项；有多个候选必须列对比表给出推荐方案与理由、写明集成方式与必要适配改造；只有当现有库无法满足需求、体积过大或存在安全风险时才允许自研，且必须在工单写明理由。检索渠道：WebSearch/WebFetch（GitHub 直连不稳定时用 api.github.com / raw.githubusercontent.com 或国内镜像）。"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

drift=0
fixed=0

# ---- 1. settings.json 必须存在且指向主理人 ----
for base in "$PLUGIN_DIR" "$CACHE_DIR"; do
  sj="$base/settings.json"
  if [ ! -f "$sj" ]; then
    echo "MISSING  ${sj}"
    drift=1
    if [ $CHECK_ONLY -eq 0 ]; then
      printf '{\n  "agent": "linkai-dev-team-team-lead"\n}\n' > "$sj"
      echo "         synced"
      fixed=$((fixed+1))
    fi
  fi
done

# ---- 2. agent MD 正文必须含"开源优先"条款 ----
for pair in $PAIRS; do
  role="${pair%%:*}"
  target="${pair##*:}"
  # 角色文件自身必须带该条款，否则视为上游被误删
  if ! grep -q "开源优先" "$ROLES_DIR/$role"; then
    echo "UPSTREAM ${role} 缺少开源优先条款，请先修复角色文件"
    drift=1
    continue
  fi
  for base in "$PLUGIN_DIR" "$CACHE_DIR"; do
    dst="$base/agents/$target"
    if [ ! -f "$dst" ]; then
      echo "MISSING  ${dst}"
      drift=1
      continue
    fi
    if grep -q "开源优先" "$dst"; then
      continue
    fi
    echo "STALE    ${dst}（缺开源优先条款）"
    drift=1
    if [ $CHECK_ONLY -eq 0 ]; then
      printf '\n%s\n%s\n' "$CLAUSE_LINE1" "$CLAUSE_LINE2" >> "$dst"
      echo "         injected"
      fixed=$((fixed+1))
    fi
  done
done

# ---- 3. devops 是新增成员，必须登记进 plugin.json 的 agents/memberAgents/members ----
for base in "$PLUGIN_DIR" "$CACHE_DIR"; do
  pj="$base/.codebuddy-plugin/plugin.json"
  if [ ! -f "$pj" ]; then
    echo "MISSING  ${pj}"
    drift=1
    continue
  fi
  if grep -q '"devops"' "$pj"; then
    continue
  fi
  echo "STALE    ${pj}（未登记 devops 成员）"
  drift=1
  if [ $CHECK_ONLY -eq 0 ]; then
    python3 - "$pj" <<'PY'
import json, sys, pathlib
pj = pathlib.Path(sys.argv[1])
data = json.loads(pj.read_text(encoding="utf-8"))
agents = data.setdefault("agents", [])
if "./agents/devops.md" not in agents:
    agents.insert(1, "./agents/devops.md")
team = data.setdefault("teamInfo", {})
members_agents = team.setdefault("memberAgents", [])
if "devops" not in members_agents:
    members_agents.insert(1, "devops")
members = data.setdefault("members", [])
if not any(m.get("id") == "devops" for m in members):
    entry = {
        "id": "devops",
        "displayName": {"en": "Gu Yun", "zh": "顾运"},
        "profession": {"en": "DevOps Engineer", "zh": "DevOps 工程师"},
        "avatar": "avatars/devops.png",
        "role": "member",
    }
    idx = 1
    for i, m in enumerate(members):
        if m.get("role") == "member":
            idx = i + 1
            break
    members.insert(idx, entry)
pj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
    echo "         registered"
    fixed=$((fixed+1))
  fi
done

# ---- 4. 写入后跑官方校验器 ----
if [ $CHECK_ONLY -eq 0 ] && [ -n "$VALIDATE" ] && [ -f "$VALIDATE" ]; then
  echo ""
  echo "=== validate_expert.py ==="
  python3 "$VALIDATE" "$PLUGIN_DIR" || true
fi

if [ $drift -eq 1 ] && [ $CHECK_ONLY -eq 1 ]; then
  echo "RESULT: drift detected"
  exit 1
fi
echo "RESULT: in sync (fixed=${fixed})"
