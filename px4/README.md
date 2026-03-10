# PX4 SITL + Gazebo Setup

This folder is a reference for PX4 SITL startup. The canonical data-collection and bridge script is `training/px4_teacher_collect_gz.py` (not the legacy `px4_teacher_collect.py`).

## Prerequisites
- PX4-Autopilot cloned at `~/PX4-Autopilot`
- Gazebo Harmonic installed
- `obstacles.sdf` copied into PX4 worlds dir (one-time setup):
  ```bash
  cp ~/workspace/LesnarAI/obstacles.sdf ~/PX4-Autopilot/Tools/simulation/gz/worlds/obstacles.sdf
  ```
- WSL Python venv `.venv-wsl` with `mavsdk numpy redis async-timeout` installed
- EKF2 GPS-denied config applied if needed (see `../px4_config/gps_denied.params`)

## SITL Startup (WSL — always use native WSL, not `/mnt/...`)

```bash
# Step 1: Start Gazebo FIRST and wait ~15s for world to load
cd ~/workspace/LesnarAI
gz sim -v4 -r obstacles.sdf

# Step 2: In a new terminal, connect PX4 to the running Gazebo instance
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
export PX4_GZ_WORLD="obstacles"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

Expected: `INFO [commander] Ready for takeoff!` and world `/world/obstacles` confirmed active.

## Teacher Data Collection

Use `training/px4_teacher_collect_gz.py` (current script — **not** the legacy `px4_teacher_collect.py`).

```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate
mkdir -p dataset/px4_teacher logs
python3 training/px4_teacher_collect_gz.py \
  --duration 0 \
  --mavsdk-server auto \
  --hz 5 \
  --alt 12 \
  --base_speed 1.2 \
  --max_speed 2.5
```

Verify data is recording:
```bash
wc -l dataset/px4_teacher/telemetry_*.csv
```

## Bridge-Only Mode (app-controlled, no autonomous flight)

```bash
python3 training/px4_teacher_collect_gz.py --duration 0 --mavsdk-server auto --bridge_only
```

## Notes
- Always start Gazebo before PX4 (world needs time to load).
- The obstacle world has 85 obstacles; the A* planner avoids them automatically in autonomous mode.
- For GPS-denied validation, apply EKF2 optical flow + rangefinder params and verify with `ekf2 status` in MAVLink console.
