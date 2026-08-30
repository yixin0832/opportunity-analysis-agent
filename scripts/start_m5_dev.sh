#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/uvicorn" ]; then
  echo "未找到后端虚拟环境或 uvicorn。"
  echo "请先执行：python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'"
  exit 1
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "未找到前端依赖。"
  echo "请先执行：cd frontend && npm install"
  exit 1
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}}"

echo "启动后端：http://127.0.0.1:${BACKEND_PORT}"
PYTHONPATH=. .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}" &
BACKEND_PID=$!

cleanup() {
  kill "${BACKEND_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "启动前端：http://127.0.0.1:${FRONTEND_PORT}"
cd frontend
exec npm run dev -- --hostname 127.0.0.1 --port "${FRONTEND_PORT}"
