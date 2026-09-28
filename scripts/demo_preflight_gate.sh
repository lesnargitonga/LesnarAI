#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_URL="${API_URL:-http://127.0.0.1:5000/api/drones}"
API_KEY="${API_KEY:-${LESNAR_ADMIN_API_KEY:-}}"
MODEL_NAME="${MODEL_NAME:-x500_0}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
SLEEP_S="${SLEEP_S:-3}"

if [[ -z "$API_KEY" ]]; then
  if [[ -f "$REPO_DIR/.env" ]]; then
    API_KEY="$(grep -E '^LESNAR_ADMIN_API_KEY=' "$REPO_DIR/.env" | sed 's/^LESNAR_ADMIN_API_KEY=//' | tr -d '[:space:]')"
  fi
fi

if [[ -z "$API_KEY" ]]; then
  echo "ERROR: missing admin API key. Set LESNAR_ADMIN_API_KEY or API_KEY." >&2
  exit 1
fi

check_model() {
  gz model --list 2>/dev/null | grep -q "^    - ${MODEL_NAME}$"
}

check_backend() {
  local payload
  payload="$(curl -s -H "X-API-Key: ${API_KEY}" "${API_URL}" || true)"
  echo "$payload" | grep -q '"drone_id":"SENTINEL-01"'
}

show_pose() {
  gz model -m "$MODEL_NAME" -p 2>/dev/null || true
}

attempt_fix() {
  echo "Attempting recovery: respawn PX4 drone..."
  pkill -9 -f '/PX4-Autopilot/.*/bin/px4|make px4_sitl gz_x500' 2>/dev/null || true
  sleep 1
  nohup "$REPO_DIR/scripts/spawn_px4_drone.sh" >/tmp/lesnar-spawn.log 2>&1 &
  sleep "$SLEEP_S"
}

echo "=== Demo Preflight Gate ==="
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  model_ok=0
  backend_ok=0

  if check_model; then
    model_ok=1
  fi

  if check_backend; then
    backend_ok=1
  fi

  if [[ "$model_ok" -eq 1 && "$backend_ok" -eq 1 ]]; then
    echo "PASS: drone model and backend telemetry are present."
    show_pose
    exit 0
  fi

  echo "Preflight attempt ${attempt}/${MAX_ATTEMPTS} failed: model_ok=${model_ok} backend_ok=${backend_ok}"
  if [[ "$attempt" -lt "$MAX_ATTEMPTS" ]]; then
    attempt_fix
  fi
done

echo "FAIL: demo preflight gate did not confirm live drone visibility." >&2
echo "Run these manually and retry:" >&2
echo "  ./scripts/start_gz_world.sh" >&2
echo "  ./scripts/spawn_px4_drone.sh" >&2
echo "  source .venv-wsl/bin/activate && python3 training/px4_teacher_collect_gz.py --duration 0 --system 127.0.0.1:14540 --mavsdk-server auto --hz 5 --alt 12 --base_speed 1.2 --max_speed 2.5 --out dataset/px4_teacher/telemetry_live.csv" >&2
exit 1
