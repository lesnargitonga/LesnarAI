#!/usr/bin/env bash
# Simple: Start sim with visible drone

set -e

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
WORKSPACE="$HOME/workspace/LesnarAI"

# Clean start
pkill -9 -f 'gz|px4|make' 2>/dev/null || true
sleep 2

echo "==> Starting Gazebo with obstacles world..."
cd "$PX4_DIR"

# Point Gazebo to our world file
export GZ_SIM_RESOURCE_PATH="$WORKSPACE:$GZ_SIM_RESOURCE_PATH"
export PX4_GZ_WORLDS="$WORKSPACE"

# Start PX4 SITL with Gazebo and drone (spawns at 0,0,2)
PX4_GZ_MODEL_POSE="0,0,2,0,0,0" PX4_GZ_WORLD="obstacles" make px4_sitl gz_x500
