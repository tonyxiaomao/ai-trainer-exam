#!/usr/bin/env bash
# 一键启动本地练习页（点选作答 + 即时判分）
#
#   ./start.sh                  入口页：选级别 → 完整题库 / 模拟考题
#   ./start.sh 3                三级入口页
#   ./start.sh 4                四级入口页
#   ./start.sh 3 题库            三级 完整题库目录（判断题/单选题/多选题）
#   ./start.sh 3 模拟            三级 模拟卷说明页（两种组卷方式）
#   ./start.sh 3 模拟 1          三级 模拟卷，只抽有答案的题（可自动判分）
#   ./start.sh 3 判断题 1 20     直接刷：三级 判断题 第 1-20 题
#   ./start.sh 3 随机 20         直接刷：三级 跨题型随机 20 题
#   PORT=8800 ./start.sh         指定端口（被占用会自动顺延）
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LEVEL="${1:-3}"
KIND="${2:-}"
A="${3:-1}"
B="${4:-20}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ 没找到 python3。macOS/Linux 一般自带；Windows 请到 https://www.python.org/downloads/ 安装后重试。" >&2
  exit 1
fi

cd "$DIR"

if [ -z "$KIND" ]; then
  echo "启动中… ${LEVEL}级 入口页"
  exec python3 scripts/web.py --level "$LEVEL" --mode home --port "${PORT:-8765}"
fi

case "$KIND" in
  题库|bank)
    echo "启动中… ${LEVEL}级 完整题库目录"
    exec python3 scripts/web.py --level "$LEVEL" --mode bank --port "${PORT:-8765}"
    ;;
  模拟|模拟考|exam)
    if [ "$A" = "1" ]; then
      echo "启动中… ${LEVEL}级 模拟卷（只抽有答案的题）"
      exec python3 scripts/web.py --level "$LEVEL" --mode exam --graded --port "${PORT:-8765}"
    fi
    echo "启动中… ${LEVEL}级 模拟卷说明页"
    exec python3 scripts/web.py --level "$LEVEL" --mode exam --port "${PORT:-8765}"
    ;;
  随机|random)
    N="${A:-20}"
    echo "启动中… ${LEVEL}级 全库随机 ${N} 道"
    exec python3 scripts/web.py --level "$LEVEL" --mode random --n "$N" --port "${PORT:-8765}"
    ;;
  随机答案|random-graded)
    N="${A:-20}"
    echo "启动中… ${LEVEL}级 随机 ${N} 道（只抽有答案的题）"
    exec python3 scripts/web.py --level "$LEVEL" --mode random --n "$N" --graded --port "${PORT:-8765}"
    ;;
  *)
    echo "启动中… ${LEVEL}级 ${KIND} 第 ${A}-${B} 题"
    exec python3 scripts/web.py --level "$LEVEL" --type "$KIND" --from "$A" --to "$B" --port "${PORT:-8765}"
    ;;
esac
