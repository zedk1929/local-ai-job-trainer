#!/usr/bin/env bash
set -e

# Apprentice launcher
echo "=========================================================="
echo " Starting Apprentice (Hackathon Skeleton)"
echo " Mode: Preview Mode (deterministic fixtures enabled)"
echo "=========================================================="

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Trap Ctrl+C to terminate both servers
cleanup() {
  echo ""
  echo "Shutting down servers..."
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Start Backend
echo "Starting Backend (FastAPI on http://127.0.0.1:8000)..."
cd "$ROOT_DIR/backend"
if command -v uv >/dev/null 2>&1; then
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
else
  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
fi
BACKEND_PID=$!

# 2. Start Frontend
echo "Starting Frontend (Vite on http://localhost:5173)..."
cd "$ROOT_DIR/frontend"
npm run dev -- --host 127.0.0.1 &
FRONTEND_PID=$!

echo ""
echo "App is ready! Open your browser at:"
echo "👉 http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers."

wait
