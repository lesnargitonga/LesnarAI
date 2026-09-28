#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_DIR/frontend"
PORT="${PORT:-3000}"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

# Prevent stale React dev servers from binding alternate ports with old bundles.
pkill -f "react-scripts/scripts/start.js|react-scripts start" 2>/dev/null || true
sleep 1

cd "$FRONTEND_DIR"
export HOST="${HOST:-0.0.0.0}"
export PORT
export BROWSER="${BROWSER:-none}"

exec npm run start:raw
