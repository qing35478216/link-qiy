#!/usr/bin/env bash
# 契约破坏性变更检测（oasdiff）
#
# 用法：
#   bash scripts/diff.sh                # 对比工作区契约 vs git HEAD（CI 用这个）
#   bash scripts/diff.sh <base> <rev>   # 对比指定的两个文件
#
# 契约冻结门禁的两半：
#   spectral 管「写得规不规范」（npm run lint）
#   oasdiff  管「改得兼不兼容」（本脚本）
# 检出破坏性变更时必须升版本号，并在 CHANGELOG.md 写明迁移说明。

set -uo pipefail

cd "$(dirname "$0")/.."

if ! command -v oasdiff >/dev/null 2>&1; then
  echo "[contracts] 未找到 oasdiff，请先安装："
  echo "  INSTALL_DIR=\$HOME/.homebrew/bin sh -c \"\$(curl -fsSL https://raw.githubusercontent.com/oasdiff/oasdiff/main/install.sh)\""
  exit 1
fi

# 显式传两个文件就直接比
if [ "$#" -eq 2 ]; then
  # 坑：oasdiff breaking 默认退出码恒为 0（--fail-on 默认 NONE），
#     直接拿来当 CI 门禁会「检出问题却不拦截」。必须显式 --fail-on ERR。
exec oasdiff breaking --fail-on ERR "$1" "$2"
fi

files=$(find openapi -type f \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null || true)
if [ -z "$files" ]; then
  echo "[contracts] openapi/ 下暂无契约文件，跳过破坏性变更检测"
  exit 0
fi

# git show 要的是相对仓库根的路径，取一下当前子目录前缀
prefix=$(git rev-parse --show-prefix 2>/dev/null || echo "")

tmp_base=$(mktemp -d)
trap 'rm -rf "$tmp_base"' EXIT

# 坑：契约通过 ../schemas/*.yaml 跨文件引用。若只把单个契约文件导出到临时目录，
#     oasdiff 解析 ../schemas 会直接失败（no such file or directory）。
#     所以必须连同 schemas/ 一起导出，保持 openapi/ 与 schemas/ 的相对层级。
mkdir -p "$tmp_base/openapi" "$tmp_base/schemas"
for s in schemas/*.yaml schemas/*.yml; do
  [ -f "$s" ] || continue
  git show "HEAD:${prefix}${s}" > "$tmp_base/schemas/$(basename "$s")" 2>/dev/null || true
done

failed=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  base_file="$tmp_base/$f"
  mkdir -p "$(dirname "$base_file")"
  if git show "HEAD:${prefix}${f}" > "$base_file" 2>/dev/null; then
    echo "── 检测 $f"
    if ! oasdiff breaking "$base_file" "$f"; then
      failed=1
    fi
  else
    echo "── 跳过 $f（git HEAD 中无此文件，视为新增）"
  fi
done <<< "$files"

if [ "$failed" -ne 0 ]; then
  echo ""
  echo "[contracts] ✗ 检测到破坏性变更：请升版本号并在 CHANGELOG.md 记录迁移说明"
  exit 1
fi

echo "[contracts] ✓ 无破坏性变更"
