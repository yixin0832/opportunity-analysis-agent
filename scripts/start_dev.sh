#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/uvicorn" ]; then
  echo "未找到 .venv 或 uvicorn，正在提示安装步骤。"
  echo "请先执行：python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'"
  exit 1
fi

echo "启动 Agent 后端 Mock 版本：http://127.0.0.1:8000/docs"
exec .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
