#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="http://localhost:5000"
USERNAME="${LESNAR_USER:-lesnar}"
PASSWORD="${LESNAR_PASS:-lesnar1234}"
DRONE_ID="${DRONE_ID:-SENTINEL-01}"
CYCLES="${CYCLES:-3}"
TAKEOFF_ALT="${TAKEOFF_ALT:-8}"
HOVER_SEC="${HOVER_SEC:-3}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]
  --username <user>
  --password <pass>
  --backend-url <url>
  --drone-id <id>
  --cycles <n>
  --takeoff-alt <m>
  --hover-sec <sec>
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username) USERNAME="${2:-}"; shift 2 ;;
    --password) PASSWORD="${2:-}"; shift 2 ;;
    --backend-url) BACKEND_URL="${2:-}"; shift 2 ;;
    --drone-id) DRONE_ID="${2:-}"; shift 2 ;;
    --cycles) CYCLES="${2:-}"; shift 2 ;;
    --takeoff-alt) TAKEOFF_ALT="${2:-}"; shift 2 ;;
    --hover-sec) HOVER_SEC="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

SESSION_HEADER="$(python3 "$PROJECT_DIR/scripts/request_session_token.py" --backend-url "$BACKEND_URL" --username "$USERNAME" --password "$PASSWORD")"

api_get() {
  curl -fsS -H "$SESSION_HEADER" "$BACKEND_URL$1"
}

api_post() {
  local path="$1"
  local data="$2"
  curl -fsS -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" -d "$data" "$BACKEND_URL$path"
}

get_state_json() {
  local raw
  raw="$(api_get "/api/drones")"
  python3 - "$DRONE_ID" "$raw" <<'PY'
import json, sys
target = sys.argv[1]
raw = sys.argv[2]
data = json.loads(raw)
for drone in data.get('drones') or []:
    if (drone.get('drone_id') or '').strip() == target:
        print(json.dumps(drone))
        raise SystemExit(0)
print(json.dumps({}))
raise SystemExit(1)
PY
}

wait_for_expr() {
  local label="$1"
  local timeout="$2"
  local expr="$3"
  local started
  started="$(date +%s)"
  while true; do
    local state
    local verdict
    if ! state="$(get_state_json 2>/dev/null || true)"; then
      state='{}'
    fi
    verdict="$(python3 - "$state" "$expr" <<'PY'
import json
import sys

state = json.loads(sys.argv[1])
expr = sys.argv[2]
safe_globals = {'__builtins__': {}}
safe_locals = {
    'state': state,
    'bool': bool,
    'float': float,
    'abs': abs,
    'max': max,
    'min': min,
}
print('1' if eval(expr, safe_globals, safe_locals) else '0')
PY
)"
    if [[ "$verdict" == "1" ]]; then
      echo "[ok] $label"
      return 0
    fi
    if (( $(date +%s) - started >= timeout )); then
      echo "[fail] Timeout waiting for: $label" >&2
      echo "[detail] Last state: $state" >&2
      return 1
    fi
    sleep 1
  done
}

echo "[check] Ensuring drone is present..."
wait_for_expr "drone present" 30 "bool(state)"

echo "[check] Forcing grounded baseline if needed..."
api_post "/api/drones/$DRONE_ID/land" '{}' >/dev/null 2>&1 || true
wait_for_expr "grounded baseline" 30 "(not bool(state.get('armed'))) and abs(float(state.get('altitude') or 0.0)) < 1.0"

passes=0
for cycle in $(seq 1 "$CYCLES"); do
  echo "[cycle $cycle/$CYCLES] arm"
  api_post "/api/drones/$DRONE_ID/arm" '{}' >/tmp/lesnar_smoke_arm.json || true
  wait_for_expr "armed" 20 "bool(state.get('armed'))"

  echo "[cycle $cycle/$CYCLES] takeoff"
  api_post "/api/drones/$DRONE_ID/takeoff" "{\"altitude\":$TAKEOFF_ALT}" >/tmp/lesnar_smoke_takeoff.json || true
  wait_for_expr "airborne" 35 "bool(state.get('in_air')) and float(state.get('altitude') or 0.0) >= max(1.5, float($TAKEOFF_ALT) * 0.5)"

  echo "[cycle $cycle/$CYCLES] hover ${HOVER_SEC}s"
  sleep "$HOVER_SEC"

  echo "[cycle $cycle/$CYCLES] land"
  api_post "/api/drones/$DRONE_ID/land" '{}' >/tmp/lesnar_smoke_land.json || true
  wait_for_expr "landed" 40 "(not bool(state.get('armed'))) and abs(float(state.get('altitude') or 0.0)) < 1.0"

  passes=$((passes + 1))
  echo "[pass] cycle $cycle complete"
done

echo "[done] $passes/$CYCLES smoke cycles passed"
