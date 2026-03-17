# Incident Report & Resolution: SITL Spawn Timeout in High-Density Environments

**Component:** Simulation Initialization Pipeline (PX4 SITL + Gazebo Harmonic)
**Status:** Resolved
**Date:** March 14, 2026

---

## 1. Executive Summary
During the transition from an empty default simulation to a high-density training environment (`obstacles.sdf` containing 200+ entities), the PX4 Autopilot failed to spawn the `x500` drone airframe. 

The system threw a `Service call timed out` error and aborted. This document outlines the root cause and the permanent dual-phase resolution required to stabilize the Reinforcement Learning (RL) data factory.

## 2. Root Cause Analysis (RCA)
The failure was not a compatibility issue, but a **deterministic race condition** between the Gazebo physics engine and the PX4 `gz_bridge`.

1. **The Physics Bottleneck:** When loading `obstacles.sdf`, Gazebo's Entity Component Manager (ECM) locks the main thread to calculate collision meshes, gravity, and mass for over 200 individual buildings and trees.
2. **The PX4 Timeout:** By design, the PX4 launch sequence allocates exactly **5 seconds** for the simulator to respond to an entity injection request (`/create` service).
3. **The Collision:** Because Gazebo was blocked computing heavy dynamic physics for the environment, it failed to answer PX4's service call within the 5-second window, causing PX4 to abort the spawn and leave a zombie process in the background.

Additionally, applying dynamic physics to 200+ stationary objects cratered the simulation's **Real-Time Factor (RTF)**, which would render AI training mathematically impossible due to extreme latency.

---

## 3. Permanent Resolution

To fix this, the system requires two configuration changes: **World Optimization** (to fix the RTF) and **Staged Initialization** (to bypass the timeout).

### Phase 1: World Optimization (The Physics Patch)
To achieve an RTF of 1.0+ for AI training, all non-moving environment features must be tagged as `<static>true</static>`. This tells Gazebo to generate collision boundaries but ignore gravity and momentum calculations.

**Action:** Run the following Python script once to permanently optimize `obstacles.sdf`.

```python
# File: scripts/patch_world.py
import re
import os

file_path = 'obstacles.sdf'

if not os.path.exists(file_path):
    print(f"Error: {file_path} not found.")
    exit(1)

with open(file_path, 'r') as f:
    content = f.read()

if '<static>true</static>' in content:
    print("✅ World is already optimized.")
else:
    # Inject <static>true</static> into all model definitions
    pattern = r'(<model\s+name="[^"]+">)'
    replacement = r'\1\n      <static>true</static>'
    new_content = re.sub(pattern, replacement, content)
    
    with open(file_path, 'w') as f:
        f.write(new_content)
    print("✅ SUCCESS: Injected static physics tags into all obstacles.")

```

**Execution:** `python3 scripts/patch_world.py`

### Phase 2: Staged Initialization (Standalone Mode)

We must decouple Gazebo's launch from PX4's launch using `PX4_GZ_STANDALONE=1`. This allows Gazebo infinite time to load the environment before PX4 attempts to connect.

**Action:** Use the following terminal workflow to launch the simulation.

**Terminal 1 (Start the Physics Engine):**
*This terminal sets the resource path so Gazebo can locate the `x500` mesh, then loads the world.*

```bash
cd ~/PX4-Autopilot
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$(pwd)/Tools/simulation/gz/models
gz sim -v4 -r ~/workspace/LesnarAI/obstacles.sdf

```

*(Wait for the GUI to open and the buildings to render).*

**Terminal 2 (Start the Autopilot Brain):**
*This terminal kills any ghost processes, prevents PX4 from trying to start its own Gazebo instance, and injects the drone into the running world.*

```bash
killall -9 px4
cd ~/PX4-Autopilot
export PX4_GZ_STANDALONE=1
export PX4_GZ_WORLD=obstacles
make px4_sitl gz_x500

```

---

## 4. Verification Protocol

To verify the system is ready for the RL Data Factory:

1. Ensure the drone is physically visible in the Gazebo GUI.
2. Check the bottom-right corner of the Gazebo GUI. The **RTF (Real-Time Factor)** must be `~1.00`. (If it is `< 0.50`, Phase 1 was not executed).
3. Execute the Teacher data collection script:
```bash
python3 training/px4_teacher_collect_gz.py --duration 60 --out dataset/px4_teacher/telemetry_adv.csv

```


4. Verify `telemetry_adv.csv` is populated with flight data.
