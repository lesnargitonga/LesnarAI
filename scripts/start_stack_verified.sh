#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_LOG="${FRONTEND_LOG:-/tmp/lesnar-frontend.log}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:3000}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:5000}"
ORCH_LOG="${ORCH_LOG:-/tmp/lesnar-orchestrator.log}"
ORCH_URL="${ORCH_URL:-http://127.0.0.1:8765/health}"

# Storage plan: keep long-lived datasets + proof artifacts on the J: SSD mount.
# This avoids growing the WSL distro disk (often hosted on C:) during long collection runs.
LESNAR_DATA_ROOT="${LESNAR_DATA_ROOT:-/mnt/j/LesnarData}"
LESNAR_ARCHIVE_ROOT="${LESNAR_ARCHIVE_ROOT:-}"
LESNAR_AUDIT_CHAIN_FILE="${LESNAR_AUDIT_CHAIN_FILE:-/mnt/j/LesnarArchive/audit_chain.jsonl}"

cd "$REPO_DIR"

docker compose up -d --build backend redis timescaledb adminer

pkill -f "scripts/runtime_orchestrator.py" 2>/dev/null || true
mkdir -p "$LESNAR_DATA_ROOT" "/mnt/j/LesnarArchive" 2>/dev/null || true

export LESNAR_DATA_ROOT
export LESNAR_ARCHIVE_ROOT
export LESNAR_AUDIT_CHAIN_FILE

# Performance + sync defaults (override by exporting before calling this script).
export LESNAR_GZ_HEADLESS="${LESNAR_GZ_HEADLESS:-1}"
export LESNAR_GZ_VERBOSITY="${LESNAR_GZ_VERBOSITY:-2}"
export LESNAR_ORCH_MODEL_CACHE_MAX_AGE_S="${LESNAR_ORCH_MODEL_CACHE_MAX_AGE_S:-120}"
export LESNAR_TEACHER_BRIDGE_ONLY="${LESNAR_TEACHER_BRIDGE_ONLY:-1}"

nohup python3 "$REPO_DIR/scripts/runtime_orchestrator.py" >"$ORCH_LOG" 2>&1 &

for i in {1..20}; do
  if curl -fsS "$ORCH_URL" >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 20 ]]; then
    echo "runtime orchestrator failed to start" >&2
    exit 1
  fi
  sleep 1
done

pkill -f "react-scripts/scripts/start.js|react-scripts start" 2>/dev/null || true
sleep 1

nohup "$REPO_DIR/scripts/start_frontend_guarded.sh" >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

python3 "$REPO_DIR/scripts/smoke_runtime.py" \
  --frontend-url "$FRONTEND_URL" \
  --backend-url "$BACKEND_URL" \
  --adminer-url "${ADMINER_URL:-http://127.0.0.1:8080}" \
  --retries 20 \
  --delay 2

echo "verified stack is ready"
echo "frontend pid=$FRONTEND_PID"
echo "frontend url=$FRONTEND_URL"
echo "backend url=$BACKEND_URL"
echo "orchestrator url=${ORCH_URL%/health}"
