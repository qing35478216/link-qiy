#!/usr/bin/env bash
# 契约 lint 门禁入口
#
# 用法：
#   bash scripts/lint.sh                    仅 error 级失败（日常 PR）
#   bash scripts/lint.sh --fail-severity=warn   冻结契约前，warn 也当失败
#
# 为什么包一层脚本：
#   spectral 在 glob 匹配不到任何文件时以退出码 2 退出。Phase 0 早期
#   openapi/ 还是空的（契约由 T-001 编写），裸跑会让 CI 无谓变红。
#   这里先探测文件，没有就跳过；契约一落地自动恢复严格门禁。

set -euo pipefail

cd "$(dirname "$0")/.."

files=()
while IFS= read -r f; do
  files+=("$f")
done < <(find openapi schemas -type f \( -name '*.yaml' -o -name '*.yml' \) 2>/dev/null || true)

if [ "${#files[@]}" -eq 0 ]; then
  echo "[contracts] openapi/ 与 schemas/ 下暂无契约文件，跳过 lint"
  exit 0
fi

echo "[contracts] 检查 ${#files[@]} 个契约文件"
exec ./node_modules/.bin/spectral lint --ruleset .spectral.yaml "${files[@]}" "$@"
