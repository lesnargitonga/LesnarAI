#!/bin/bash
# Fix for Gazebo timeout issue
# This script starts Gazebo first, waits for it to be ready, then starts PX4

set -e

echo "=== Starting Gazebo + PX4 SITL ==="

# Kill any existing instances
pkill -9 px4 || true
pkill -9 gz || true
sleep 2

# Start Gazebo in background
echo "[1/3] Starting Gazebo simulator..."
gz sim -v4 -r ~/PX4-Autopilot/Tools/simulation/gz/worlds/default.sdf &
GZ_PID=$!

# Wait for Gazebo to be ready (check if gz service is responding)
echo "[2/3] Waiting for Gazebo to be ready..."
for i in {1..30}; do
    if gz service -l | grep -q "/world/default"; then
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
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500

# Cleanup on exit
trap "kill $GZ_PID 2>/dev/null || true" EXIT
