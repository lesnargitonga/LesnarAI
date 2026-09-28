#!/usr/bin/env bash
# LESNAR AI demo-safe runner.
#
# Brings up the operator stack WITHOUT Docker, real Postgres, PX4, or Gazebo, and
# seeds SIMULATED drones through the real backend API so the dashboard shows a
# real state change. No real drone, flight, or hardware is involved.
#
#   Backend (Flask + Socket.IO) : http://127.0.0.1:5000
#   Runtime orchestrator        : http://127.0.0.1:8765   (control plane only; Gazebo/PX4 stay OFF)
#   Frontend (React)            : http://127.0.0.1:3006
#
# Uses a throwaway SQLite DB (/tmp/lesnar-demo.db), never the real .env/Postgres.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="${PY:-$REPO_ROOT/.venv/bin/python}"
BACKEND_URL="http://127.0.0.1:5000"
ORCH_URL="http://127.0.0.1:8765"
SEED="$REPO_ROOT/demo/lesnarai_demo_seed.json"

start_backend() {
  echo ">> starting backend on $BACKEND_URL"
  PYTHONPATH=backend:drone_simulation \
  env -u DATABASE_URL -u POSTGRES_USER -u POSTGRES_PASSWORD -u POSTGRES_DB \
    DATABASE_URL="sqlite:////tmp/lesnar-demo.db" \
    REDIS_HOST=127.0.0.1 REDIS_PORT=6379 \
    LESNAR_REQUIRE_AUTH=0 LESNAR_ENFORCE_AUDIT_CHAIN=0 \
    AUTO_MIGRATE=1 ALLOW_UNSAFE_WERKZEUG=1 \
    nohup "$PY" backend/app.py >/tmp/lesnar-backend.log 2>&1 &
}

start_orchestrator() {
  echo ">> starting runtime orchestrator on $ORCH_URL (control plane only)"
  LESNAR_ORCH_HOST=127.0.0.1 LESNAR_ORCH_PORT=8765 LESNAR_DATA_ROOT=/tmp/lesnar-demo-data \
    nohup "$PY" scripts/runtime_orchestrator.py >/tmp/lesnar-orch.log 2>&1 &
}

start_frontend() {
  echo ">> starting frontend on http://127.0.0.1:3006"
  PORT=3006 HOST=127.0.0.1 BROWSER=none \
    REACT_APP_BACKEND_URL="$BACKEND_URL" \
    REACT_APP_API_BASE_URL="$BACKEND_URL" \
    REACT_APP_ORCHESTRATOR_URL="$ORCH_URL" \
    REACT_APP_REQUIRE_SESSION_AUTH=0 \
    nohup npm --prefix frontend run start:raw >/tmp/lesnar-frontend.log 2>&1 &
}

wait_for() { for _ in $(seq 1 30); do curl -sf "$1" >/dev/null 2>&1 && return 0; sleep 1; done; return 1; }

seed_drones() {
  echo ">> seeding SIMULATED drones via real backend API"
  "$PY" - "$SEED" "$BACKEND_URL" <<'PY'
import json, sys, urllib.request
seed_path, base = sys.argv[1], sys.argv[2]
seed = json.load(open(seed_path))
for d in seed["simulated_drones"]:
    body = json.dumps(d).encode()
    req = urllib.request.Request(f"{base}/api/drones", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("  +", d["drone_id"], "->", json.load(r).get("message") or json.load(r))
    except Exception as e:
        print("  =", d["drone_id"], "already present or", e)
with urllib.request.urlopen(f"{base}/api/telemetry", timeout=10) as r:
    t = json.load(r)["fleet_status"]
    print("  fleet_status:", t)
PY
}

case "${1:-up}" in
  up)
    pgrep -f "backend/app.py" >/dev/null || start_backend
    pgrep -f "runtime_orchestrator.py" >/dev/null || start_orchestrator
    pgrep -f "start:raw" >/dev/null || start_frontend
    wait_for "$BACKEND_URL/api/health" && echo ">> backend healthy"
    wait_for "$ORCH_URL/health" && echo ">> orchestrator healthy"
    seed_drones
    echo ">> LESNAR AI demo-safe stack is up. Dashboard: http://127.0.0.1:3006"
    ;;
  seed) seed_drones ;;
  *) echo "usage: $0 [up|seed]"; exit 1 ;;
esac
