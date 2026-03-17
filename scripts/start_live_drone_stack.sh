#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv-wsl}"
SIM_LOG="${SIM_LOG:-$REPO_DIR/logs/px4_gz_live.out}"
TEACHER_LOG="${TEACHER_LOG:-$REPO_DIR/logs/teacher_live.out}"
SYSTEM_ADDR="${SYSTEM_ADDR:-127.0.0.1:14540}"

mkdir -p "$REPO_DIR/logs" "$REPO_DIR/dataset/px4_teacher"

if [[ ! -x "$REPO_DIR/scripts/start_px4_gz.sh" ]]; then
  echo "missing launcher: $REPO_DIR/scripts/start_px4_gz.sh" >&2
  exit 1
fi

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "missing virtualenv: $VENV_DIR" >&2
  exit 1
fi

pkill -f 'px4_teacher_collect_gz.py|mavsdk_server' 2>/dev/null || true
sleep 1

nohup "$REPO_DIR/scripts/start_px4_gz.sh" >"$SIM_LOG" 2>&1 &
SIM_PID=$!

for _ in {1..45}; do
  if gz service -l 2>/dev/null | grep -q '/world/obstacles'; then
    break
  fi
  sleep 1
done

for _ in {1..45}; do
  if ss -lun | grep -q ':14540'; then
    break
  fi
  sleep 1
done

source "$VENV_DIR/bin/activate"
nohup python3 "$REPO_DIR/training/px4_teacher_collect_gz.py" \
  --duration 0 \
  --system "$SYSTEM_ADDR" \
  --mavsdk-server auto \
  --hz 5 \
  --alt 12 \
  --base_speed 1.2 \
  --max_speed 2.5 \
  --out "$REPO_DIR/dataset/px4_teacher/telemetry_live.csv" >"$TEACHER_LOG" 2>&1 &
TEACHER_PID=$!

echo "live drone stack launch requested"
echo "sim pid=$SIM_PID"
echo "teacher pid=$TEACHER_PID"
echo "sim log=$SIM_LOG"
echo "teacher log=$TEACHER_LOG"