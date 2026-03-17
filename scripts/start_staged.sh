#!/usr/bin/env bash
# Staged initialization - Proper fix for obstacles world drone spawn
# Separates Gazebo world loading from drone spawning to avoid timeout

set -e

WORKSPACE="$HOME/workspace/LesnarAI"
PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"

echo "=== LESNAR AI: Staged Initialization Protocol ==="
echo ""

# Clean slate
echo "[1/4] Terminating existing processes..."
pkill -9 -f 'gz sim|px4|make px4' 2>/dev/null || true
sleep 2

# Stage 1: Launch Gazebo world ONLY (no drone yet)
echo "[2/4] Launching Gazebo with obstacles world..."
gz sim -v4 -r "$WORKSPACE/obstacles.sdf" >/dev/null 2>&1 &
GZ_PID=$!
echo "  Gazebo started (PID: $GZ_PID)"

# Stage 2: Wait for world to be fully initialized and responsive
echo "[3/4] Waiting for world initialization (this may take 20-30s with 200+ obstacles)..."
READY=false
for i in {1..60}; do
  # Test if world control service actually responds (not just exists)
  if timeout 2 gz service -s /world/obstacles/control \
     --reqtype gz.msgs.WorldControl \
     --reptype gz.msgs.Boolean \
     --req 'pause: false' 2>/dev/null | grep -q 'data: true'; then
    echo "  ✓ Gazebo world fully initialized and responsive"
    READY=true
    break
  fi
  
  # Progress indicator
  if [[ $((i % 5)) -eq 0 ]]; then
    echo "  ... still initializing ($i/60s)"
  fi
  sleep 1
done

if [[ "$READY" != "true" ]]; then
  echo "  ✗ TIMEOUT: Gazebo world did not become responsive in 60s"
  echo "  Check if Gazebo GUI opened successfully"
  exit 1
fi

sleep 2

# Stage 3: Manually spawn drone into ready world
echo "[4/4] Spawning x500 drone at (0, 0, 2.5)..."
DRONE_SDF="$PX4_DIR/Tools/simulation/gz/models/x500/model.sdf"

if [[ ! -f "$DRONE_SDF" ]]; then
  echo "  ✗ ERROR: Drone model not found at $DRONE_SDF"
  exit 1
fi

# Spawn via Gazebo service (world is ready, should succeed immediately)
SPAWN_RESULT=$(cat "$DRONE_SDF" | gz service -s /world/obstacles/create \
  --reqtype gz.msgs.EntityFactory \
  --reptype gz.msgs.Boolean \
  --req 'sdf: "-", name: "x500_0", pose: {position: {x: 0, y: 0, z: 2.5}}' 2>&1)

if echo "$SPAWN_RESULT" | grep -q "data: true"; then
  echo "  ✓ Drone spawned successfully"
else
  echo "  ✗ Drone spawn failed: $SPAWN_RESULT"
  exit 1
fi

sleep 2

# Verify spawn
if gz model --list 2>/dev/null | grep -q "x500_0"; then
  echo "  ✓ Drone confirmed in model list"
else
  echo "  ✗ WARNING: Drone not in model list (may still be initializing)"
fi

# Stage 4: Launch PX4 autopilot to connect to existing drone
echo ""
echo "=== Starting PX4 Autopilot ==="
cd "$PX4_DIR"

export PX4_GZ_MODEL_NAME="x500_0"
export PX4_GZ_WORLD="obstacles"
export PX4_SYS_AUTOSTART="4001"

echo "PX4 will now connect to drone x500_0 in world 'obstacles'..."
echo ""

# Run PX4 in foreground so user sees output
build/px4_sitl_default/bin/px4 \
  -d build/px4_sitl_default/etc \
  -s etc/init.d-posix/rcS
