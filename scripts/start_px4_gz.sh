#!/bin/bash
# Fix for Gazebo timeout issue
# This script starts Gazebo first, waits for it to be ready, then starts PX4

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORLD_FILE="${PX4_GZ_WORLD_FILE:-$PROJECT_DIR/obstacles.sdf}"

echo "=== Starting Gazebo + PX4 SITL ==="

if [ ! -f "$WORLD_FILE" ]; then
    echo "ERROR: World file not found: $WORLD_FILE"
    exit 1
fi

# Kill any existing instances
pkill -9 px4 || true
pkill -9 gz || true
sleep 2

# Start Gazebo in background
echo "[1/3] Starting Gazebo simulator..."
echo "    World file: $WORLD_FILE"
gz sim -v4 -r "$WORLD_FILE" &
GZ_PID=$!

# Wait for Gazebo to be ready (check if gz service is responding)
echo "[2/3] Waiting for Gazebo to be ready..."
for i in {1..30}; do
    if gz service -l | grep -q "/world/obstacles"; then
        echo "Gazebo is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: Gazebo failed to start in time"
        kill $GZ_PID 2>/dev/null || true
        exit 1
    fi
    echo "Waiting... ($i/30)"
    sleep 1
done

# Now start PX4 with increased timeout
echo "[3/3] Starting PX4 SITL..."
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500

# Cleanup on exit
trap "kill $GZ_PID 2>/dev/null || true" EXIT
