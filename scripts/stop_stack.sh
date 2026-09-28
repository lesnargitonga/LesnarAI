#!/usr/bin/env bash
set -euo pipefail

# Stops the app stack so you can restart cleanly (prevents "address already in use" and stray terminals).

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Stop sim/runtime actors first.
if command -v curl >/dev/null 2>&1; then
  curl -fsS -X POST http://127.0.0.1:8765/kill-all >/dev/null 2>&1 || true
fi

# Stop background dev servers.
pkill -f "scripts/runtime_orchestrator.py" 2>/dev/null || true
pkill -f "react-scripts/scripts/start.js|react-scripts start" 2>/dev/null || true

# Stop docker services.
docker compose down >/dev/null 2>&1 || true

echo "stack stopped"
