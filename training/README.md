# Training Pipeline

This directory contains the teacher bridge and student training code for Operation Sentinel.

## Overview

Training follows a teacher-student imitation learning approach:

1. **Teacher bridge** (`px4_teacher_collect_gz.py`) flies the drone autonomously in Gazebo Harmonic, executing A\* navigation and collecting high-frequency telemetry.
2. **Student training** (`train_student_px4.py`) trains a lightweight navigation policy from the collected CSV data.

The teacher bridge is both the live operator bridge (receiving commands from the frontend via Redis) and the data collector. A single run produces one CSV file containing the complete flight record.

## Prerequisites

Install the training virtual environment inside the repo root:

```bash
cd ~/workspace/LesnarAI
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -r training/requirements.txt
```

PyTorch is required for student training only:

```bash
pip install -r training/requirements-pytorch.txt
```

The teacher bridge also requires MAVSDK Python:

```bash
pip install mavsdk
```

## Collecting Training Data

### Method 1 — Frontend (recommended)

With the full stack running (`./scripts/start_stack_verified.sh`) and the simulation spawned:

1. Open `http://127.0.0.1:3000`
2. Navigate to the drone in the fleet list
3. Click **START TRAINING**

The frontend dispatches a 4-waypoint box mission (25 m sides, 10 m altitude) centred on the drone's current GPS position. The teacher bridge arms the drone, executes AUTO.TAKEOFF, then transitions to Offboard mode once the drone has physically climbed to near the target altitude, and navigates the full pattern. Telemetry is written continuously to the current run CSV.

Each run is stored at:

```
$LESNAR_DATA_ROOT/px4_teacher/runs/<run_id>/telemetry_live_0.csv
```

Stop the run from **Settings → Simulator Runtime Orchestrator → INSTANT KILL ALL**.

### Method 2 — Headless scenario runner

For automated overnight data collection:

```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate

# Single autonomous run, 120 s flight window
python3 scripts/scenario_runner.py --count 1 --duration-s 120

# Overnight batch with randomised controller settings
python3 scripts/scenario_runner.py \
  --fuzz --seed 42 --count 200 --duration-s 90 --continue-on-fail
```

Each run writes its telemetry under `$LESNAR_DATA_ROOT/px4_teacher/runs/`.

### Method 3 — Manual teacher invocation (development / custom args)

```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate

python3 training/px4_teacher_collect_gz.py \
  --duration 0 \
  --system 127.0.0.1:14540 \
  --mavsdk-server auto \
  --hz 5 \
  --alt 12 \
  --bridge_only \
  --drone-id x500_0 \
  --out /tmp/telemetry_run.csv
```

Use `--bridge_only` to wait for frontend/Redis commands rather than flying autonomously. Remove `--bridge_only` for fully autonomous navigation without operator input.

Key flags:

| Flag | Default | Description |
|---|---|---|
| `--system` | `127.0.0.1:14540` | MAVLink UDP address |
| `--mavsdk-server` | `auto` | Auto-launch MAVSDK server |
| `--hz` | `5` | Telemetry sample rate (Hz) |
| `--alt` | `12` | Target cruise altitude (m) |
| `--base_speed` | `1.2` | Nominal flight speed (m/s) |
| `--max_speed` | `2.5` | Maximum flight speed (m/s) |
| `--bridge_only` | off | Wait for Redis commands instead of flying autonomously |
| `--drone-id` | `x500_0` | Drone ID reported to backend |
| `--out` | auto | CSV output path |
| `--disable_wind_model` | off | Disable synthetic wind fields |
| `--enable_battery_model` | off | Add CSV-only battery model fields |
| `--duration` | `300` | Max flight duration in seconds (0 = unlimited) |

## Telemetry CSV Schema

The CSV produced by the teacher bridge includes:

| Column group | Fields |
|---|---|
| Timestamp | `timestamp` (Unix float) |
| Position | `lat`, `lon`, `rel_alt` |
| Velocity | `vx`, `vy`, `vz` (NED, m/s) |
| Commands | `cmd_vx`, `cmd_vy`, `cmd_vz` (Offboard setpoints) |
| LIDAR sim | `dist_forward`, `dist_right`, `dist_backward`, `dist_left` |
| Path tracking | `cross_track_error`, `heading_error`, `waypoint_dist` |
| Obstacle | `obs_clearance`, `obs_count_nearby` |
| FALCON metrics | `falcon_score`, `falcon_aggression`, `falcon_efficiency` |
| Battery model | `bat_voltage_model`, `bat_current_model` (if `--enable_battery_model`) |
| Environment | `wind_n`, `wind_e`, `wind_d`, `synthetic_environment` |
| GPS quality | `gps_fix_type`, `gps_satellites` |
| Flight phase | `flight_phase` (`ground`, `climb`, `cruise`, `descent`) |

A typical 90-second run at 5 Hz produces approximately 400–500 rows. The first few rows have `flight_phase=ground`; the bulk have `flight_phase=cruise`.

## Training the Student Model

After collecting one or more runs, train the student policy:

```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate

# From the most recent orchestrator run
latest_csv=$(ls -1t "${LESNAR_DATA_ROOT:-/mnt/j/LesnarData}/px4_teacher/runs"/*/telemetry_live_0.csv 2>/dev/null | head -1)
echo "Training from: $latest_csv"

python3 training/train_student_px4.py \
  --data "$latest_csv" \
  --epochs 20 \
  --bs 128 \
  --out models/student_px4_latest.pt
```

Combine multiple runs:

```bash
python3 training/train_student_px4.py \
  --data /mnt/j/LesnarData/px4_teacher/runs/*/telemetry_live_0.csv \
  --epochs 40 \
  --bs 256 \
  --out models/student_px4_combined.pt
```

The student model is a feed-forward policy network. Input features are selected from the telemetry CSV; output is the commanded velocity vector `[cmd_vx, cmd_vy, cmd_vz]`.

Verify the output:

```bash
ls -lh models/student_px4_latest.pt
```

## Data Architecture

| Path | Contents |
|---|---|
| `$LESNAR_DATA_ROOT/px4_teacher/runs/<run_id>/` | One directory per orchestrated run |
| `…/telemetry_live_0.csv` | Teacher CSV for drone 0 |
| `…/RUN.json` | Start metadata (timestamp, git rev, obstacle hash) |
| `…/MANIFEST.json` | SHA-256 hashes of all run artifacts (written on kill) |
| `dataset/px4_teacher/` | Archived reference datasets (static, not overwritten) |
| `models/` | Trained model checkpoints |

`$LESNAR_DATA_ROOT` defaults to `/mnt/j/LesnarData`. Override with the environment variable before starting the stack.

## Known Limitations

**Obstacle avoidance.** The A\* path planner uses a static obstacle grid loaded from the SDF world file at bridge startup. It does not perform real-time re-planning around dynamic obstacles or obstacles absent from the SDF. The FALCON clearance metrics in the CSV provide full observability into clearance distances; improving the planner is a planned next step.

**Closed-loop inference.** The student model is trained offline from teacher data. It is not yet wired into the teacher bridge for closed-loop autonomous control. This is the next integration target after the training pipeline is validated on larger datasets.

**Multi-drone data.** The scenario runner supports `drone_count > 1` at the orchestrator level, but parallel multi-drone training collection is not exercised routinely. Each drone writes to its own `telemetry_live_N.csv` file.
