#!/usr/bin/env bash
# WORKING drone spawn - uses PX4's world system

set -e

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
WORKSPACE="$HOME/workspace/LesnarAI"

# Kill everything
pkill -9 -f 'gz|px4|make' 2>/dev/null || true
sleep 2

echo "Setting up custom world..."
# Create link or copy so PX4 can find our world
PX4_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
mkdir -p "$PX4_WORLDS"
if [[ ! -f "$PX4_WORLDS/obstacles.sdf" ]]; then
  ln -sf "$WORKSPACE/obstacles.sdf" "$PX4_WORLDS/obstacles.sdf"
  echo "✓ Linked obstacles world to PX4 worlds directory"
fi

echo "Starting PX4 with obstacles world and drone..."
cd "$PX4_DIR"

# Drone spawns at 0,0,2 meters high (visible!)
PX4_GZ_MODEL_POSE="0,0,2,0,0,0" PX4_GZ_WORLD="obstacles" make px4_sitl gz_x500
