#!/usr/bin/env bash
set -euo pipefail

# Multi-vehicle spawn helper (staged workflow):
# - Assumes Gazebo world is already running (use scripts/start_gz_world.sh)
# - Spawns N x500 vehicles by starting N PX4 instances.
# - Uses the same PX4/GZ env vars that px4-rc.simulator consumes:
#   PX4_GZ_MODEL, PX4_GZ_MODEL_POSE, PX4_GZ_WORLD.

COUNT="${1:-2}"
if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [[ "$COUNT" -lt 1 ]]; then
  echo "usage: $0 <count>=2" >&2
  exit 2
fi

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
WORLD="${PX4_GZ_WORLD:-obstacles}"
MODEL="${PX4_GZ_MODEL:-x500}"
ALT="${PX4_GZ_SPAWN_ALT:-30.0}"
SPACING="${PX4_GZ_SPAWN_SPACING:-20.0}"

cd "$PX4_DIR"

# Ensure we have a SITL build for the px4 binary.
if [[ ! -x "build/px4_sitl_default/bin/px4" ]]; then
  make px4_sitl_default
fi

BUILD_PATH="$PX4_DIR/build/px4_sitl_default"
PX4_BIN="$BUILD_PATH/bin/px4"
ETC_DIR="$BUILD_PATH/etc"

# Provide PX4_GZ_MODELS/WORLDS + GZ_SIM_RESOURCE_PATH (what gz_env.sh normally does).
if [[ -f "$BUILD_PATH/rootfs/gz_env.sh" ]]; then
  # shellcheck disable=SC1090
  . "$BUILD_PATH/rootfs/gz_env.sh"
fi
# Keep the README's model path behavior as well.
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$PX4_DIR/Tools/simulation/gz/models"

# Clean up any previous PX4 instances.
killall -9 px4 2>/dev/null || true
sleep 1

for i in $(seq 0 $((COUNT - 1))); do
  inst_dir="$BUILD_PATH/instance_$i"
  mkdir -p "$inst_dir"

  x=$(python3 -c "print(f'{float($i)*float($SPACING):.3f}')")
  pose="${x},0,${ALT},0,0,0"

  echo "starting x500_${i} pose=${pose}"

  (
    cd "$inst_dir"
    export PX4_SIM_MODEL=gz_x500
    export PX4_GZ_WORLD="$WORLD"
    export PX4_GZ_MODEL="$MODEL"
    export PX4_GZ_MODEL_POSE="$pose"
    "$PX4_BIN" -i "$i" -d "$ETC_DIR" >out.log 2>err.log &
  )

done

echo "spawn requested: $COUNT"
