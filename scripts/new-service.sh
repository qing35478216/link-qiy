#!/usr/bin/env bash
# LinkAI 新服务脚手架：./scripts/new-service.sh <name> [--go]
# 纯模板复制 + 占位符替换，无额外工具依赖（cookiecutter 亦可，见 service-template/README.md）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="${1:-}"
GO="${2:-}"

if [[ -z "$NAME" ]]; then
  echo "用法: $0 <service-name> [--go]" >&2
  exit 1
fi
if [[ ! "$NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "服务名必须是小写字母/数字/中划线（snake_case/kebab-case）" >&2
  exit 1
fi

MODULE="${NAME//-/_}"   # python 模块名：中划线转下划线

if [[ "$GO" == "--go" ]]; then
  DEST="$ROOT/services/$NAME"
  [[ -e "$DEST" ]] && { echo "已存在: $DEST" >&2; exit 1; }
  mkdir -p "$DEST"/{cmd,internal/{handler,service,domain,infra}}
  cat > "$DEST/go.mod" <<EOF
module github.com/linkai/linkai/services/$NAME

go 1.23
EOF
  cat > "$DEST/cmd/main.go" <<EOF
package main

func main() {}
EOF
  cat > "$DEST/README.md" <<EOF
# services/$NAME

Go 服务（gateway/sandbox 类）。四层同构：handler → service → domain → internal。
健康检查统一 GET /healthz（见 scripts/service-template/README.md 硬约定）。
EOF
  echo "Go 服务骨架已生成: $DEST"
  exit 0
fi

DEST="$ROOT/services/$NAME"
[[ -e "$DEST" ]] && { echo "已存在: $DEST" >&2; exit 1; }

mkdir -p "$DEST/src/linkai_$MODULE"/{api,services,domain,infra}

sed -e "s/__SERVICE_NAME__/$NAME/g" -e "s/__MODULE__/$MODULE/g" \
  "$ROOT/scripts/service-template/pyproject.toml" > "$DEST/pyproject.toml"
sed -e "s/__SERVICE_NAME__/$NAME/g" -e "s/__MODULE__/$MODULE/g" \
  "$ROOT/scripts/service-template/env.example" > "$DEST/.env.example"
sed -e "s/__SERVICE_NAME__/$NAME/g" -e "s/__MODULE__/$MODULE/g" \
  "$ROOT/scripts/service-template/main.py" > "$DEST/src/linkai_$MODULE/main.py"
sed -e "s/__SERVICE_NAME__/$NAME/g" -e "s/__MODULE__/$MODULE/g" \
  "$ROOT/scripts/service-template/health.py" > "$DEST/src/linkai_$MODULE/api/health.py"
touch "$DEST/src/linkai_$MODULE/services/.gitkeep" \
      "$DEST/src/linkai_$MODULE/domain/.gitkeep" \
      "$DEST/src/linkai_$MODULE/infra/.gitkeep"

cat > "$DEST/README.md" <<EOF
# services/$NAME

Python 服务，四层架构（api/services/domain/infra）。本地开发：

    cd services/$NAME && uv sync && uv run uvicorn linkai_$MODULE.main:app --reload

健康检查: GET /healthz。约定见 scripts/service-template/README.md 与 docs/observability.md。
EOF

echo "Python 服务骨架已生成: $DEST"
echo "下一步: cd $DEST && uv sync，然后把 lint/test 命令挂进根 Makefile 的 gate 目标"
