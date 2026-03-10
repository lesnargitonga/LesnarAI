#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
PATTERN="$FRONTEND_DIR/node_modules/react-scripts/scripts/start.js"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "[frontend-guard] frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

echo "[frontend-guard] checking for duplicate frontend dev servers..."
PIDS="$(pgrep -f "$PATTERN" || true)"

if [[ -n "$PIDS" ]]; then
  echo "[frontend-guard] stopping existing frontend process(es): $PIDS"
  kill $PIDS || true
  sleep 1

  REMAINING="$(pgrep -f "$PATTERN" || true)"
  if [[ -n "$REMAINING" ]]; then
    echo "[frontend-guard] force-stopping stubborn process(es): $REMAINING"
    kill -9 $REMAINING || true
    sleep 1
  fi
fi

echo "[frontend-guard] starting single frontend server on PORT=${PORT:-3000}"
cd "$FRONTEND_DIR"
exec env HOST="${HOST:-0.0.0.0}" PORT="${PORT:-3000}" npm run start:raw
