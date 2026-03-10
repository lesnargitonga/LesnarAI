#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="http://localhost:5000"
USERNAME="${LESNAR_USER:-}"
PASSWORD="${LESNAR_PASS:-}"
DRONE_ID="${DRONE_ID:-SENTINEL-01}"
MAX_STALE_SECONDS="${MAX_STALE_SECONDS:-8}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --username <user> --password <pass> [options]

Options:
  --backend-url <url>      Backend URL (default: ${BACKEND_URL})
  --drone-id <id>          Drone ID to validate (default: ${DRONE_ID})
  --max-stale-seconds <n>  Max telemetry age in seconds (default: ${MAX_STALE_SECONDS})

Environment fallback:
  LESNAR_USER, LESNAR_PASS, DRONE_ID, MAX_STALE_SECONDS
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username)
      USERNAME="${2:-}"
      shift 2
      ;;
    --password)
      PASSWORD="${2:-}"
      shift 2
      ;;
    --backend-url)
      BACKEND_URL="${2:-}"
      shift 2
      ;;
    --drone-id)
      DRONE_ID="${2:-}"
      shift 2
      ;;
    --max-stale-seconds)
      MAX_STALE_SECONDS="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
  echo "[fail] Missing credentials. Provide --username/--password or LESNAR_USER/LESNAR_PASS." >&2
  exit 2
fi

echo "[check] Requesting session token..."
SESSION_HEADER="$(python3 "$PROJECT_DIR/scripts/request_session_token.py" --backend-url "$BACKEND_URL" --username "$USERNAME" --password "$PASSWORD" 2>/tmp/lesnar_preflight_auth.err || true)"
if [[ -z "$SESSION_HEADER" ]]; then
  echo "[fail] Authentication failed."
  if [[ -s /tmp/lesnar_preflight_auth.err ]]; then
    echo "[detail] $(cat /tmp/lesnar_preflight_auth.err)"
  fi
  exit 1
fi
echo "[ok] Auth header acquired."

echo "[check] Backend health..."
HEALTH_JSON="$(curl -sS -H "$SESSION_HEADER" "$BACKEND_URL/api/health" || true)"
if [[ -z "$HEALTH_JSON" ]]; then
  echo "[fail] Health endpoint unreachable at $BACKEND_URL"
  exit 1
fi
HEALTH_STATUS="$(python3 - <<'PY' "$HEALTH_JSON"
import json,sys
try:
    data=json.loads(sys.argv[1])
    print(data.get('status') or '')
except Exception:
    print('')
PY
)"
if [[ "$HEALTH_STATUS" != "ok" ]]; then
  echo "[fail] Health check not ok. Response: $HEALTH_JSON"
  exit 1
fi
echo "[ok] Backend health is ok."

echo "[check] Session validity (/api/auth/me)..."
AUTH_ME="$(curl -sS -H "$SESSION_HEADER" "$BACKEND_URL/api/auth/me" || true)"
AUTH_ME_OK="$(python3 - <<'PY' "$AUTH_ME"
import json,sys
try:
    data=json.loads(sys.argv[1])
    print('1' if data.get('success') else '0')
except Exception:
    print('0')
PY
)"
if [[ "$AUTH_ME_OK" != "1" ]]; then
  echo "[fail] Session is not valid for authenticated routes. Response: $AUTH_ME"
  exit 1
fi
echo "[ok] Session is valid."

echo "[check] Active drones and telemetry freshness..."
DRONES_JSON="$(curl -sS -H "$SESSION_HEADER" "$BACKEND_URL/api/drones" || true)"
python3 - <<'PY' "$DRONES_JSON" "$DRONE_ID" "$MAX_STALE_SECONDS"
import json,sys
from datetime import datetime, timezone

raw, target, max_stale = sys.argv[1], sys.argv[2], float(sys.argv[3])
try:
    data = json.loads(raw)
except Exception:
    print('[fail] Could not parse /api/drones response')
    sys.exit(1)

if not data.get('success'):
    print(f"[fail] /api/drones returned failure: {raw}")
    sys.exit(1)

drones = data.get('drones') or []
if not drones:
    print('[fail] No active drones detected.')
    print('       Start PX4 + teacher bridge and wait for telemetry publish.')
    sys.exit(1)

picked = None
for d in drones:
    if (d.get('drone_id') or '').strip() == target:
        picked = d
        break
if picked is None:
    available = ', '.join((d.get('drone_id') or '?') for d in drones)
    print(f"[fail] Target drone '{target}' not found. Available: {available}")
    sys.exit(1)

ts = picked.get('timestamp')
if not ts:
    print(f"[warn] Drone {target} has no timestamp; skipping staleness gate.")
    print('[ok] Preflight passed with warning.')
    sys.exit(0)

try:
    stamp = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age = (now - stamp).total_seconds()
except Exception:
    print(f"[warn] Could not parse timestamp '{ts}'; skipping staleness gate.")
    print('[ok] Preflight passed with warning.')
    sys.exit(0)

if age > max_stale:
    print(f"[fail] Drone {target} telemetry is stale ({age:.1f}s > {max_stale:.1f}s).")
    print('       Keep teacher bridge running and ensure telemetry stream is live.')
    sys.exit(1)

print(f"[ok] Drone {target} detected with fresh telemetry ({age:.1f}s old).")
print('[ready] You can now issue control commands safely.')
PY

rc=$?
if [[ $rc -ne 0 ]]; then
  exit $rc
fi

echo "[done] Preflight check completed successfully."
