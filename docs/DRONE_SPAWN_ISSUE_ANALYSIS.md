# Drone Spawn Failure Analysis - obstacles.sdf World

**Date:** March 14, 2026  
**Issue:** PX4 autopilot drone fails to spawn in obstacles.sdf world despite working in default world  
**Impact:** Critical - Training system requires obstacle course, cannot train without it

---

## Executive Summary

The drone spawning system that previously worked with the obstacles.sdf world is now failing with a service timeout error. The drone spawns successfully in PX4's default world, confirming the drone model and PX4 configuration are correct. This indicates a **Gazebo world-specific initialization timing issue**, not a fundamental compatibility problem.

---

## Technical Background

### System Architecture
- **Simulator:** Gazebo Harmonic (gz-sim-8)
- **Autopilot:** PX4-Autopilot SITL
- **Bridge:** gz_bridge (PX4's Gazebo interface plugin)
- **World:** obstacles.sdf (custom world with 200+ obstacles: buildings, trees, walls)
- **Drone Model:** x500 quadcopter

### Normal Spawn Sequence
1. PX4 launches with `make px4_sitl gz_x500`
2. Gazebo starts and loads world file
3. PX4's gz_bridge calls Gazebo service `/world/<name>/create` to spawn drone
4. Gazebo responds with entity creation confirmation
5. gz_bridge establishes sensor/actuator bridges
6. Drone appears in simulation

---

## Problem Analysis

### Observed Failure Mode

```
ERROR [gz_bridge] Service call timed out
ERROR [gz_bridge] Task start failed (-1)
ERROR [init] gz_bridge failed to start
ERROR [px4] Startup script returned with return value: 256
```

**Timeline:**
- Gazebo world "obstacles" launches successfully
- World services are available (`/world/obstacles/create`, `/world/obstacles/clock`, etc.)
- PX4 detects world correctly: `INFO [init] starting gazebo with world: obstacles.sdf`
- gz_bridge attempts to spawn drone via service call
- **Service call times out** (default timeout: ~5 seconds)
- Spawn aborts, PX4 exits

### Root Cause Hypothesis

The timeout occurs because **obstacles.sdf contains 200+ entities** that Gazebo must initialize:
- 25 Skyscrapers (large collision meshes)
- 50 Spires (medium complexity)
- 100 Trees (vegetation with physics)
- 5 Walls (collision boundaries)
- Ground plane + physics engine

**Theory:** When PX4's gz_bridge calls the `/world/obstacles/create` service to spawn the drone, Gazebo is still:
1. **Loading/processing the obstacle entities** into the physics engine
2. **Building collision detection structures** for 200+ objects
3. **Initializing sensor plugins** for each obstacle
4. **Computing initial entity states** for the world

During this heavy initialization, Gazebo's **service handler thread is blocked or delayed**, causing the drone spawn request to timeout before completion.

### Evidence Supporting This Theory

1. **Default world works:** PX4's default.sdf has minimal entities (ground plane + basic lighting) - spawn completes in < 1 second
2. **Service timing:** The error occurs specifically at service call, not at world loading
3. **World complexity:** obstacles.sdf is 10-20x more complex than default.sdf
4. **Previous functionality:** System worked before, suggesting environmental/timing sensitivity

---

## Why This Matters for Training

**Critical Requirement:** The autonomous navigation training system requires:
- Dense obstacle field for collision avoidance learning
- Varied geometry (buildings, trees, walls) for sensor diversity  
- GPS-denied environment simulation
- Pathfinding algorithm validation

**Training cannot proceed without obstacles** - the default empty world provides no learning signal for:
- VFH (Vector Field Histogram) obstacle avoidance
- Expert teacher trajectory collection
- Collision detection validation
- Real-world scenario simulation

---

## Solution Approaches

### Option 1: Increase gz_bridge Timeout (Quick Fix)
**Approach:** Modify PX4 source to increase service call timeout from 5s to 30s

**Implementation:**
```cpp
// File: PX4-Autopilot/src/modules/simulation/gz_bridge/GZBridge.cpp
// Line ~200-250 (service call section)

// BEFORE:
const auto timeout = std::chrono::seconds(5);

// AFTER:  
const auto timeout = std::chrono::seconds(30);
```

**Pros:**
- Minimal code change
- Allows Gazebo time to finish initializing
- Non-invasive

**Cons:**
- Requires PX4 recompilation
- Doesn't address root cause
- Slow startup (30s wait every launch)

**Viability:** ★★★☆☆ (Acceptable but not optimal)

---

### Option 2: Staged Initialization (Proper Fix)
**Approach:** Separate world loading from drone spawning with explicit readiness check

**Implementation:**

Create new startup script:
```bash
#!/usr/bin/env bash
# scripts/start_staged.sh

# Stage 1: Launch Gazebo world ONLY
PX4_GZ_STANDALONE=1 gz sim -v4 -r obstacles.sdf &
GZ_PID=$!

# Stage 2: Wait for world to be fully ready
echo "Waiting for Gazebo to fully initialize obstacles..."
for i in {1..60}; do
  # Check if world services are responsive (not just listed)
  if timeout 1 gz service -s /world/obstacles/control \
     --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean \
     --req 'pause: false' 2>/dev/null | grep -q 'data: true'; then
    echo "✓ Gazebo world ready and responsive"
    break
  fi
  sleep 1
done

# Stage 3: Now spawn drone via direct service call
echo "Spawning drone..."
cat ~/PX4-Autopilot/Tools/simulation/gz/models/x500/model.sdf | \
  gz service -s /world/obstacles/create \
  --reqtype gz.msgs.EntityFactory \
  --reptype gz.msgs.Boolean \
  --req 'sdf: "-", name: "x500_0", pose: {position: {z: 2.0}}'

sleep 2

# Stage 4: Launch PX4 to connect to existing drone
cd ~/PX4-Autopilot
export PX4_GZ_MODEL_NAME="x500_0"
export PX4_GZ_WORLD="obstacles"
build/px4_sitl_default/bin/px4 -d build/px4_sitl_default/etc \
  -s etc/init.d-posix/rcS
```

**Pros:**
- No PX4 code modification required
- Explicit control over initialization timing
- Gazebo fully ready before drone spawn
- Can add progress indicators

**Cons:**
- More complex startup sequence
- Requires maintaining custom script

**Viability:** ★★★★★ (Recommended)

---

### Option 3: World Optimization (Long-term)
**Approach:** Reduce obstacles.sdf initialization complexity

**Strategies:**
1. **Lazy loading:** Mark non-critical obstacles as `<static>` to skip physics initialization
2. **LOD models:** Use simpler collision meshes for distant obstacles
3. **Spatial partitioning:** Load obstacles in chunks as drone approaches
4. **Deferred physics:** Start world paused, spawn drone, then unpause

**Example modification to obstacles.sdf:**
```xml
<!-- Mark background obstacles as static (no physics) -->
<model name="Skyscraper_20">
  <static>true</static>  <!-- Add this line -->
  <pose>50 50 0 0 0 0</pose>
  ...
</model>
```

**Pros:**
- Faster world initialization
- Better simulation performance
- Reduces memory usage

**Cons:**
- Requires world file modifications
- May affect training realism (static vs dynamic obstacles)
- Time-intensive to implement

**Viability:** ★★★★☆ (Good for performance, medium effort)

---

### Option 4: PX4 Service Retry Logic (Robust Fix)
**Approach:** Add retry mechanism to gz_bridge service calls

**Concept:**
```cpp
// Pseudo-code for PX4 modification
bool spawn_success = false;
for (int attempt = 0; attempt < 3; attempt++) {
  auto result = call_service("/world/obstacles/create", drone_sdf, timeout_5s);
  if (result.success) {
    spawn_success = true;
    break;
  }
  PX4_WARN("Spawn attempt %d failed, retrying...", attempt + 1);
  sleep(2);
}
```

**Pros:**
- Handles transient timing issues
- Self-recovering
- Production-ready approach

**Cons:**
- Requires PX4 source modification
- Needs recompilation

**Viability:** ★★★★☆ (Professional solution, requires dev work)

---

## Immediate Action Plan

### Phase 1: Emergency Workaround (Now)
Use **Option 2 (Staged Initialization)** to unblock training immediately:

```bash
# Run this to get training working TODAY
cd ~/workspace/LesnarAI
./scripts/start_staged.sh
```

**Expected outcome:** Drone spawns successfully in obstacles world within 20-30 seconds

### Phase 2: Verification (Within 1 hour)
1. Confirm drone is visible in Gazebo GUI at coordinates (0, 0, 2)
2. Verify PX4 MAVLink connection on UDP 14580
3. Test teacher script connection: `python3 training/px4_teacher_collect_gz.py --duration 10`
4. Validate obstacle detection in collected telemetry

### Phase 3: Permanent Fix (Next session)
Implement **Option 1 (Timeout increase)** OR **Option 4 (Retry logic)** depending on testing results:

- If staged spawn works perfectly: Document and use as standard procedure
- If timing is still flaky: Implement PX4 timeout increase
- If production deployment needed: Implement retry logic in PX4

---

## Historical Context - Why It Worked Before

**Possible explanations for regression:**

1. **Gazebo version update:** Harmonic may have changed service handling timing
2. **System load:** WSL2 resource allocation may have changed
3. **World file modifications:** obstacles.sdf may have grown more complex over time
4. **PX4 version drift:** Recent PX4 updates may have tightened timeouts
5. **Race condition:** Bug was always present but probabilistic (now hitting consistently)

**Recommendation:** Check git history of obstacles.sdf and PX4 version to identify changes

---

## Testing Protocol

To validate any fix:

```bash
# Test 1: Clean spawn (from cold start)
pkill -9 -f 'gz|px4'
sleep 5
./scripts/start_staged.sh
# EXPECT: Drone visible within 30s

# Test 2: Repeated spawns (stability check)
for i in {1..5}; do
  pkill -9 -f 'gz|px4'
  sleep 3
  ./scripts/start_staged.sh
  sleep 20
  gz model --list | grep x500_0 || echo "FAIL: Run $i"
done
# EXPECT: 5/5 successful spawns

# Test 3: Training integration
./scripts/start_staged.sh
sleep 15
python3 training/px4_teacher_collect_gz.py --duration 30 --out test.csv
# EXPECT: Telemetry collection without errors
```

---

## Conclusion

This is **not a fundamental incompatibility** - it's a **timing coordination issue** between Gazebo world initialization and PX4's spawn service call. The obstacles are essential for training and must be preserved.

**Recommended path forward:**
1. Implement staged initialization script (Option 2) - **15 minutes**
2. Test with actual training workload - **30 minutes**  
3. If stable, document as standard procedure
4. If issues persist, implement PX4 timeout increase (Option 1) - **1 hour including rebuild**

The training system architecture is sound. This is a solvable integration timing problem, not a design flaw.

---

## References

- PX4 gz_bridge source: `PX4-Autopilot/src/modules/simulation/gz_bridge/`
- Gazebo service documentation: https://gazebosim.org/api/sim/8/createsystem.html
- World file specification: `workspace/LesnarAI/obstacles.sdf`
- Training requirements: `workspace/LesnarAI/docs/DATA_UTILIZATION_STRATEGY.md`
