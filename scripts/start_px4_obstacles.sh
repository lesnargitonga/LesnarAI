#!/bin/bash
# Launch PX4 SITL with custom obstacles world
set -e

echo "=== Starting PX4 SITL with Obstacles World ==="

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORLD_FILE="$PROJECT_DIR/obstacles.sdf"
PX4_DIR="$HOME/PX4-Autopilot"

# Verify world file exists
if [ ! -f "$WORLD_FILE" ]; then
    echo "ERROR: obstacles.sdf not found at $WORLD_FILE"
    exit 1
fi

# Kill any existing instances
pkill -9 px4 || true
pkill -9 gz || true
sleep 2

cd "$PX4_DIR"

# Set environment variables for custom world
export PX4_GZ_WORLD="$WORLD_FILE"
export PX4_GZ_MODEL_NAME="x500_0"
export PX4_GZ_MODEL="x500"

echo "[*] Launching PX4 SITL with obstacles world..."
echo "    World file: $WORLD_FILE"
echo "    Model: x500"

# Run PX4 SITL
make px4_sitl gz_x500
