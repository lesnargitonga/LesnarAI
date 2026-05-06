# Operation Sentinel

Operation Sentinel is the LesnarAI command-and-control stack for autonomous UAV simulation, data collection, and student-model training. It integrates PX4 SITL, Gazebo Harmonic, a Gunicorn-served Flask/Socket.IO backend, a React operator frontend, and a MAVSDK-based teacher bridge that drives the drone and collects flight telemetry.

## Showcase Focus

- Systems integration across robotics simulation, web operations, telemetry, and training.
- Truth-first fleet control: the UI only reflects real simulation and telemetry state.
- Reproducible, auditable runtime artifacts for each launch and mission run.

## At a Glance

- Operator dashboard for real-time UAV command and fleet visibility.
- PX4 SITL and Gazebo Harmonic simulation orchestration.
- MAVSDK teacher bridge for flight control and telemetry capture.
- Redis and TimescaleDB-backed messaging and telemetry pipelines.
- Training-data collection for downstream student-policy learning.

## System Overview

| Component | Technology | Port |
|---|---|---|
| Operator UI | React (CRA dev server) | 3000 |
| Backend API | Flask + Gunicorn + Socket.IO | 5000 |
| Database | TimescaleDB (Postgres) in Docker | 5432 |
| DB Admin | Adminer in Docker | 8080 |
| Message bus | Redis in Docker | 6379 |
| Simulation | Gazebo Harmonic + PX4 SITL (`x500`) | — |
| Teacher bridge | `training/px4_teacher_collect_gz.py` | — |
| Runtime orchestrator | `scripts/runtime_orchestrator.py` | 8765 |
| MAVSDK server | Auto-launched by teacher bridge | 50051 |

Run artifacts are written to `$LESNAR_DATA_ROOT/px4_teacher/runs/<run_id>/` and include a locked `MANIFEST.json` with SHA-256 hashes of every artifact.

## Design Principles

**Truth-first.** Drone existence in the UI is gated by Gazebo ground truth via the runtime orchestrator `/models` endpoint. The backend runs in external-only mode (`LESNAR_EXTERNAL_ONLY=1`) by default — drones are registered only when real MAVSDK telemetry arrives on the Redis `telemetry` channel. No phantom assets, no synthesised KPIs.

**Auditable runs.** Every `/launch-all` creates an immutable run directory. Every `/kill-all` finalises it with a SHA-256 manifest and an optional signed audit-chain entry.

**Environment stressors are labelled.** Wind and air-density fields are simulated for training realism and published under a clearly marked `environment.synthetic_environment: true` key. They are never substituted for real sensor data.

## Prerequisites

- WSL2 (Ubuntu 22.04 or 24.04) with home directory on the native Linux filesystem (e.g. `/home/lesnar/`)
- Docker Desktop with WSL integration enabled
- PX4-Autopilot source at `~/PX4-Autopilot` (built at least once with `make px4_sitl gz_x500`)
- Gazebo Harmonic (`gz-harmonic`) installed in WSL
- Python 3.12 virtual environment at `.venv-wsl/`
- Node.js ≥ 18 for the frontend

> **Do not run from `/mnt/...` paths.** File-locking and performance issues are known when the working directory is on the Windows NTFS mount. All terminals must `cd ~/workspace/LesnarAI` first.

Quick sanity check:

```bash
cd ~/workspace/LesnarAI
realpath .   # must not start with /mnt
```

## Quickstart — Full Stack

```bash
cd ~/workspace/LesnarAI
./scripts/start_stack_verified.sh
```

This script:
1. Rebuilds and starts TimescaleDB, Redis, and the backend container
2. Starts Adminer
3. Starts the runtime orchestrator on port `8765`
4. Kills any stale React dev servers, then starts a clean one on port `3000`
5. Runs an end-to-end smoke test and exits non-zero on any failure

Gazebo and PX4 are **not** started by this script. Launch them from the frontend (see below) or from the CLI.

Default Gazebo mode: headless (`LESNAR_GZ_HEADLESS=1`). To re-enable the GUI:

```bash
LESNAR_GZ_HEADLESS=0 ./scripts/start_stack_verified.sh
```

## Launching the Simulation

### Option A — Frontend (recommended)

After `start_stack_verified.sh` is running, open `http://127.0.0.1:3000`, navigate to **Settings → Simulator Runtime Orchestrator**, and press **SPAWN CLUSTER**.

This starts Gazebo, spawns the PX4 `x500` drone, and launches the teacher bridge — all in one action. Status indicators for Gazebo, PX4, Teacher Bridge, and the drone model update in real time.

Press **INSTANT KILL ALL** to stop the simulation and finalise the run manifest.

### Option B — CLI via orchestrator

```bash
# Start Gazebo world (headless)
./scripts/start_sim.sh

# Launch drone + teacher via the orchestrator
curl -s -X POST http://127.0.0.1:8765/launch-all \
  -H 'Content-Type: application/json' \
  -d '{"drone_count": 1, "gz_headless": true}'

# Stop and finalise
curl -s -X POST http://127.0.0.1:8765/kill-all
```

### Option C — Manual staged launch (debugging only)

For diagnosing Gazebo entity-loading timeouts with the 200+ obstacle world:

**Terminal 1 — Physics engine:**
```bash
cd ~/PX4-Autopilot
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$(pwd)/Tools/simulation/gz/models
gz sim -v4 -r ~/workspace/LesnarAI/obstacles.sdf
```
Wait 10–20 s for the world to fully load.

**Terminal 2 — PX4 SITL:**
```bash
killall -9 px4 2>/dev/null; true
cd ~/PX4-Autopilot
export PX4_GZ_STANDALONE=1
export PX4_GZ_WORLD=obstacles
make px4_sitl gz_x500
```

**Terminal 3 — Teacher bridge:**
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
  --out /tmp/telemetry_manual.csv
```

## Flight Control from the Frontend

Once the stack and simulation are running:

1. Open `http://127.0.0.1:3000` and log in (`lesnar` / `LesnarAdmin2026!`).
2. The drone `x500_0` appears in the fleet list once telemetry is received.
3. Available operator actions:
   - **ARM** — arms the motors
   - **TAKEOFF** — arms + takes off to the configured altitude
   - **LAND** — commands a controlled landing
   - **DISARM** — disarms (ground only)
   - **GOTO** — flies to a clicked map coordinate via A\* path planning
   - **START TRAINING** — dispatches a 4-waypoint box mission around the drone's current GPS position; the teacher bridge arms, takes off, and navigates autonomously while collecting telemetry

All commands are published to the Redis `commands` channel and consumed by the teacher bridge in real time. PX4 mode transitions (Auto.Takeoff → Offboard) are managed inside the bridge.

## Runtime Orchestrator

`scripts/runtime_orchestrator.py` is a lightweight HTTP service on port `8765`.

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/status` | GET | Process state + cached Gazebo model list |
| `/models` | GET | Live Gazebo model list (UI ground truth) |
| `/launch-all` | POST | Start Gazebo + PX4 + teacher bridge(s) |
| `/kill-all` | POST | Stop all runtime processes + finalise manifest |

`/launch-all` body (all fields optional):

```json
{
  "drone_count": 1,
  "gz_headless": true,
  "teacher_args": ["--base_speed", "2.8", "--max_speed", "5.0"]
}
```

`teacher_args` are appended verbatim to each `px4_teacher_collect_gz.py` invocation, enabling per-run controller and stressor overrides without editing scripts.

### Run directory layout

Every `/launch-all` creates:

```
$LESNAR_DATA_ROOT/px4_teacher/runs/<run_id>/
├── RUN.json              # start metadata, git rev, obstacle hash
├── telemetry_live_0.csv  # teacher CSV (pre-created, filled during flight)
├── scenario.json         # (scenario runner only)
├── outcomes.json         # (scenario runner only)
└── MANIFEST.json         # SHA-256 hashes of all artifacts (written on /kill-all)
```

`$LESNAR_DATA_ROOT` defaults to `/mnt/j/LesnarData`. Override with the environment variable.

## Teacher Bridge and Telemetry

`training/px4_teacher_collect_gz.py` has two modes:

| Mode | Flag | Behaviour |
|---|---|---|
| **Bridge-only** | `--bridge_only` | Subscribes to Redis `commands`; arms/takes off/navigates on operator instruction; collects telemetry |
| **Autonomous** | _(no flag)_ | Immediately arms, takes off, and runs A\* autonomous navigation with no operator input |

Telemetry CSV columns include: timestamp, GPS (lat/lon), relative altitude, NED velocity, commanded velocity, LIDAR simulation, cross-track error, heading error, obstacle clearance, FALCON metrics, battery model fields, GPS quality, and flight phase.

**Wind and environment model.** Wind is enabled by default for training realism. All synthetic environment fields are published under `environment.synthetic_environment: true` and are never substituted for real sensor data. Disable with `--disable_wind_model`.

**Battery model.** Off by default. Enable CSV-only battery/power model fields with `--enable_battery_model`. Real battery telemetry from MAVSDK is never overridden.

**Known limitation — obstacle avoidance.** The current A\* path planner uses a pre-loaded static obstacle grid from the SDF world file. Dynamic obstacle avoidance (real-time re-planning around moving obstacles or obstacles not present in the SDF) is not yet implemented. This is a planned improvement.

## Headless Scenario Runner

For automated multi-run data collection:

```bash
# Single run, 120 s
python3 scripts/scenario_runner.py --count 1 --duration-s 120

# Overnight fuzz — randomises controller aggressiveness
python3 scripts/scenario_runner.py \
  --fuzz --seed 1337 --count 5000 --duration-s 90 --continue-on-fail

# From a scenario file
python3 scripts/scenario_runner.py \
  --scenarios scripts/scenarios.example.json --continue-on-fail
```

Each run writes `scenario.json` and `outcomes.json` into its run directory before manifest finalisation.

## Student Model Training

After one or more collection runs:

```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate
pip install -r training/requirements.txt   # first time only

# Train from the most recent orchestrator run
latest_csv=$(ls -1t "${LESNAR_DATA_ROOT:-/mnt/j/LesnarData}/px4_teacher/runs"/*/telemetry_live_0.csv 2>/dev/null | head -1)
python3 training/train_student_px4.py \
  --data "$latest_csv" \
  --epochs 20 \
  --bs 128 \
  --out models/student_px4_latest.pt
```

See `training/README.md` for full training pipeline documentation.

## Authentication

Runtime authentication is Postgres-backed (session tokens).

| Role | Username | Default credential |
|---|---|---|
| Admin | `lesnar` | `LesnarAdmin2026!` |
| Operator | `sentinnel` | set in DB / `manage_auth_users.py` |
| Viewer | `viewer` | set in DB / `manage_auth_users.py` |

Manage users interactively:

```bash
python3 scripts/manage_auth_users.py
```

API keys are configured in `.env`. Read active values from `.env` directly.

## Service Endpoints

| Service | URL |
|---|---|
| Operator UI | `http://127.0.0.1:3000` |
| Backend API | `http://127.0.0.1:5000` |
| Runtime orchestrator | `http://127.0.0.1:8765` |
| Adminer | `http://127.0.0.1:8080` |
| Postgres | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

Adminer login (local compose network):

- System: `PostgreSQL` / Server: `timescaledb` / Database: `lesnar`
- Username and password: from `.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`)

## Verification

```bash
# Backend liveness
curl -s http://127.0.0.1:5000/

# Login
curl -s -X POST http://127.0.0.1:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"lesnar","password":"LesnarAdmin2026!"}'

# Full smoke test
python3 scripts/smoke_runtime.py

# Pre-flight gate (confirms drone model + telemetry are present)
./scripts/demo_preflight_gate.sh

# Live drone watch
watch -n 1 "curl -s -H 'X-API-Key: <operator_key>' http://127.0.0.1:5000/api/drones"

# Runtime orchestrator status
curl -s http://127.0.0.1:8765/status | python3 -m json.tool
```

## Data Storage

| Data type | Storage |
|---|---|
| Flight telemetry (training input) | CSV per run (`telemetry_live_*.csv`) |
| Auth users and sessions | Postgres (`auth_users`, `auth_sessions` tables) |
| Security and audit events | Postgres + optional `audit_chain.jsonl` |
| Process output | `logs/` + container stdout |

At scale, CSV archives should be converted to Parquet for training pipelines. Operational and security events remain in Postgres.

## Troubleshooting

### Drone does not appear in the frontend

Check in order:

1. `curl -s http://127.0.0.1:8765/status` → `gz_running: true`, `px4_running: true`, `teacher_running: true`
2. `curl -s http://127.0.0.1:8765/models` → lists `x500_0`
3. `curl -s -H 'X-API-Key: ...' http://127.0.0.1:5000/api/drones` → `count: 1`

If Gazebo is up but the drone model is missing, respawn:

```bash
python3 scripts/spawn_direct.py
gz model --list | grep x500
```

If the teacher is running but the backend shows 0 drones, a stale `mavsdk_server` process may be holding port 50051:

```bash
pkill -9 -f 'mavsdk_server'
curl -s -X POST http://127.0.0.1:8765/kill-all
curl -s -X POST http://127.0.0.1:8765/launch-all \
  -H 'Content-Type: application/json' -d '{"drone_count":1,"gz_headless":true}'
```

The orchestrator's `instant_kill()` includes a `mavsdk_server` cleanup step to prevent this automatically.

### Frontend shows on a different port or looks stale

```bash
cd ~/workspace/LesnarAI/frontend
npm start
```

`npm start` routes through `scripts/start_frontend_guarded.sh`, which kills stale React processes before starting a clean instance on port `3000`.

### Training mission starts but drone never takes off

This was a confirmed bug fixed March 2026. Symptom: drone arms and teacher logs "External mission armed," but altitude stays at ~0.06 m indefinitely with lateral velocity commands.

**Root cause 1**: PX4 SITL sets `in_air=True` almost immediately after the takeoff command (before physical liftoff). The old offboard transition check triggered at ground level, cancelling `AUTO.TAKEOFF` and sending zero vertical velocity.

**Root cause 2**: `current_path = [(px0, py0)]` caused an immediate false "waypoint reached" signal, advancing the mission to waypoint 2 before the drone moved.

Both fixes are applied in `training/px4_teacher_collect_gz.py`. If this symptom reappears in a future build, verify:
- Offboard mode only activates once `rel_alt ≥ max(2.0, target_alt − 1.5)`
- Waypoint advancement is skipped while `await_takeoff_alt is not None`

### Adminer login fails

Use Server: `timescaledb` (not `localhost`). Username and password come from `.env`. If the container is not running:

```bash
docker compose up -d adminer timescaledb
```

### Backend is up but session login fails

Re-run the full verified script:

```bash
./scripts/start_stack_verified.sh
```

This re-creates the backend container and re-applies all migrations.

## Known Limitations and Planned Work

| Area | Current state | Planned |
|---|---|---|
| Obstacle avoidance | Static A\* grid, pre-loaded from SDF at startup | Real-time replanning with dynamic obstacles |
| Gazebo memory usage | May be OOM-killed after ~2 min on memory-constrained hosts | Lighter world SDF / reduced obstacle count option |
| Multi-drone | `drone_count > 1` supported by orchestrator but not regularly exercised | Fleet coordination and multi-agent training |
| Student model inference | Model trained offline; not used for closed-loop control | Inference integration into teacher bridge |

## Key Source Files

| File | Role |
|---|---|
| `scripts/runtime_orchestrator.py` | Process lifecycle, run manifest, HTTP API |
| `scripts/start_stack_verified.sh` | Canonical bring-up with smoke test |
| `scripts/smoke_runtime.py` | End-to-end health verification |
| `scripts/scenario_runner.py` | Headless multi-run automation |
| `training/px4_teacher_collect_gz.py` | MAVSDK bridge, A\* navigation, telemetry collection |
| `training/train_student_px4.py` | Student policy training from collected CSV |
| `backend/app.py` | Flask API, Redis command dispatch, telemetry ingestion |
| `frontend/src/components/DroneList.js` | Primary operator control panel |
| `frontend/src/context/DroneContext.js` | Fleet state management and API wrappers |
