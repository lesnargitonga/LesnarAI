# Operation Sentinel

## Overview

Operation Sentinel is a local, offline-capable drone autonomy and command and control stack.
It is designed for simulation in PX4 SITL with Gazebo Harmonic.

The canonical execution model is split by responsibility.
Windows hosts Docker Desktop.
Ubuntu in WSL2 hosts PX4 and Gazebo.

## 🚀 Complete Setup Guide (A-Z)

**Prerequisites:**
- ✅ Windows 10/11 with WSL2 (Ubuntu 22.04)
- ✅ Docker Desktop running with WSL integration
- ✅ PX4-Autopilot installed at `~/PX4-Autopilot` in WSL

---

### Step A: Start Backend Services (WSL Terminal 1)

```bash
cd ~/lesnar/LesnarAI
docker compose --env-file .env.example down -v
docker compose --env-file .env.example up -d
```

**Wait 20 seconds**, then verify:
```bash
curl -H "X-API-Key: example-operator-key" http://localhost:5000/api/health
```
**Expected:** `{"status":"ok"}`

---

### Step B: Start Gazebo with Obstacles (WSL Terminal 1 - same)

```bash
cd ~/lesnar/LesnarAI
gz sim -v4 -r obstacles.sdf &
```

**⏱️ WAIT 15 SECONDS** - Gazebo GUI will open showing:
- 25 colored skyscrapers
- 50 red spires
- 10 green trees
- Empty sky (drone will spawn next)

---

### Step C: Start PX4 Autopilot (WSL Terminal 1 - same)

```bash
sleep 15
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

**Expected output:** `INFO [commander] Ready for takeoff!`

**✅ Check Gazebo:** You should now see the x500 drone spawned among the obstacles.

---

### Step D: Start Bridge Script (WSL Terminal 2 - NEW TERMINAL)

```bash
cd ~/lesnar/LesnarAI
source .venv-wsl/bin/activate
mkdir -p dataset/px4_teacher
python training/px4_teacher_collect_gz.py --duration 300 --base_speed 6.0 --max_speed 12.0
```

**Expected output:**
```
[INFO] --> Redis connected (Bridge Established) at 127.0.0.1:6379
[INFO] --> Connected!
[INFO] --> Arming...
[INFO] --> Starting A* Pathfinding (ONLINE)...
```

**Note:** Speed increased to 6-12 m/s for better presentation visibility.

---

### Step E: View Database (Browser)

Open in your browser: **http://localhost:8080**

**Login credentials:**
- Server: `timescaledb`
- Username: `lesnar`
- Password: `example-password`
- Database: `lesnar`

**Click on tables to view:**
- `drones` - Registered drones
- `flight_log` - Real-time telemetry (refreshing)
- `command_logs` - Command history

---

### Step F: View Frontend Dashboard (Browser)

Open in your browser: **http://localhost:3000**

*(Frontend must be running - see Optional Frontend section below)*

---

### Step G: Test API Commands (WSL Terminal 3 or Windows PowerShell)

**Check drone status:**
```bash
curl -H "X-API-Key: example-operator-key" http://localhost:5000/api/drones | jq
```
**Expected:** Shows `SENTINEL-01` with position, battery, etc.

**Command takeoff:**
```bash
curl -X POST -H "X-API-Key: example-operator-key" \
  -H "Content-Type: application/json" \
  -d '{"altitude": 10}' \
  http://localhost:5000/api/drones/SENTINEL-01/takeoff
```
**Watch Gazebo:** Drone lifts off to 10 meters

**Navigate to waypoint:**
```bash
curl -X POST -H "X-API-Key: example-operator-key" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 47.3977, "longitude": 8.5456, "altitude": 50}' \
  http://localhost:5000/api/drones/SENTINEL-01/goto
```
**Watch Gazebo:** Drone navigates avoiding obstacles using A* pathfinding

**Land:**
```bash
curl -X POST -H "X-API-Key: example-operator-key" \
  http://localhost:5000/api/drones/SENTINEL-01/land
```
**Watch Gazebo:** Drone descends and lands

---

## 🌐 All URLs for Presentation

| Service | URL | Purpose |
|---------|-----|---------|
| **Backend API** | http://localhost:5000 | REST API for drone control |
| **API Health** | http://localhost:5000/api/health | Backend health check |
| **API Drones** | http://localhost:5000/api/drones | List registered drones |
| **Adminer (Database)** | http://localhost:8080 | View telemetry in TimescaleDB |
| **Frontend Dashboard** | http://localhost:3000 | React UI (if running) |

---

## 📦 Optional: Frontend Dashboard

```bash
# WSL Terminal (separate from others)
cd ~/lesnar/LesnarAI/frontend
npm start
```

Then open: **http://localhost:3000**

---

## 🎯 Quick Reference

**API Key:** `example-operator-key`
**Database Password:** `example-password`
**Drone ID:** `SENTINEL-01`

**Key Files:**
- Obstacles: `obstacles.sdf` (85 obstacles)
- Bridge: `training/px4_teacher_collect_gz.py`
- Backend: `backend/app.py`

## Requirements

### Windows

1. Windows 10 or Windows 11
2. WSL2 enabled with Ubuntu 22.04 installed
3. Docker Desktop, recommended, with WSL integration enabled

### Ubuntu in WSL2

1. Base tooling
    ```bash
    sudo apt update
    sudo apt install -y git curl jq python3 python3-venv python3-pip build-essential
    ```

2. Node.js LTS, recommended via nvm
    ```bash
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    source ~/.bashrc
    nvm install --lts
    ```

3. Docker CLI available in WSL
    ```bash
    docker version
    docker compose version
    ```

## Repository location

Run PX4 and Gazebo from the WSL filesystem.
Do not run heavy simulation workloads from `/mnt/c` or `/mnt/d`.

If the repository currently resides on a Windows drive, copy it into WSL.
```bash
mkdir -p ~/lesnar/LesnarAI
rsync -a --delete "/mnt/<drive>/path/to/repo/" ~/lesnar/LesnarAI/
cd ~/lesnar/LesnarAI
```

## Docker networking modes

There are two supported setups.

1. Recommended
    Docker Desktop with WSL integration.
    From WSL, `docker compose up` works.
    From WSL, Redis is reachable at `127.0.0.1:6379`.

2. Alternative
    Docker runs only on Windows with no WSL integration.
    In this mode, WSL cannot reach Redis at `127.0.0.1:6379`.
    Obtain the Windows host IP from WSL.
    ```bash
    export WINDOWS_HOST=$(grep nameserver /etc/resolv.conf | awk '{print $2}')
    echo "$WINDOWS_HOST"
    ```

## Start backend services

1. Choose an environment file
    For non sensitive smoke tests, use `.env.example`.
    For local development, copy `.env.example` to `.env` and replace all values.

2. Start services
    ```bash
    docker compose --env-file .env.example up -d --build
    docker compose --env-file .env.example ps
    ```

3. Default endpoints
    Backend API is `http://localhost:5000`.
    Adminer is `http://localhost:8080`.

4. Keys and configuration
    The backend enforces `X-API-Key` when keys are configured.
    For smoke tests, `.env.example` uses non sensitive placeholder keys.

## Frontend

1. Create `frontend/.env` for API authentication
    ```bash
    set -a; source .env.example; set +a
    echo "REACT_APP_API_KEY=$LESNAR_OPERATOR_API_KEY" > frontend/.env
    echo "REACT_APP_BACKEND_URL=http://localhost:5000" >> frontend/.env
    ```

2. Start the development server
    ```bash
    cd frontend
    npm ci
    npm start
    ```

3. Optional, build only
    ```bash
    npm run build
    ```

## PX4 SITL and Gazebo

1. Install PX4 and dependencies
    ```bash
    cd ~
    git clone --recursive https://github.com/PX4/PX4-Autopilot
    bash PX4-Autopilot/Tools/setup/ubuntu.sh
    ```

2. **Copy obstacles world to PX4** (one-time setup)
    ```bash
    cp ~/lesnar/LesnarAI/obstacles.sdf ~/PX4-Autopilot/Tools/simulation/gz/worlds/obstacles.sdf
    ```

3. **Start Gazebo with obstacles world FIRST**
    ```bash
    cd ~/lesnar/LesnarAI
    gz sim -v4 -r obstacles.sdf &
    ```
    
    Wait 10-15 seconds for Gazebo GUI to open showing:
    - 25 colored skyscrapers (80-150m tall)
    - 50 red spires (200m tall)
    - 10 green trees (ground level)

4. **Then start PX4 to connect to running Gazebo**
    ```bash
    sleep 10
    cd ~/PX4-Autopilot
    export PX4_GZ_MODEL="x500"
    PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
    ```

The x500 drone will spawn in Gazebo among the obstacles. PX4 exposes MAVLink on UDP port 14540 by default.

**Note:** The two-step startup (Gazebo first, then PX4) is required because the obstacles world is large (85 obstacles) and needs time to load before PX4 connects.

## Bridge process

1. Create a Python virtual environment
    ```bash
    cd ~/lesnar/LesnarAI
    python3 -m venv .venv-wsl
    source .venv-wsl/bin/activate
    pip install -U pip
    pip install mavsdk numpy redis async-timeout
    ```

2. Start the bridge process
    Recommended Docker mode uses Redis at 127.0.0.1.
    ```bash
    python3 training/px4_teacher_collect_gz.py \
      --system udpin://0.0.0.0:14540 \
      --drone-id SENTINEL-01 \
      --redis-host 127.0.0.1 \
      --redis-port 6379 \
      --mavsdk-server auto
    ```

If Docker runs only on Windows, replace `--redis-host 127.0.0.1` with `--redis-host $WINDOWS_HOST`.

## Smoke test

Run these from WSL unless you are using the Windows only Docker mode.

1. Confirm containers
    ```bash
    docker compose --env-file .env.example up -d --build
    docker compose --env-file .env.example ps
    docker compose --env-file .env.example exec -T redis redis-cli ping
    ```

2. Confirm backend authentication
    ```bash
    set -a; source .env.example; set +a
    curl -s -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" http://localhost:5000/api/health | jq .status
    ```

3. Confirm the bridge appears as a drone
    ```bash
    set -a; source .env.example; set +a
    curl -s -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" http://localhost:5000/api/drones | jq '.drones[].drone_id'
    ```

4. Confirm command propagation
    ```bash
    set -a; source .env.example; set +a
    curl -s -X POST -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" -H "Content-Type: application/json" \
      http://localhost:5000/api/drones/SENTINEL-01/takeoff -d '{"altitude":10}' | jq .

    curl -s -X POST -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" -H "Content-Type: application/json" \
      http://localhost:5000/api/drones/SENTINEL-01/goto -d '{"latitude":40.7129,"longitude":-74.0061,"altitude":10}' | jq .

    curl -s -X POST -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" -H "Content-Type: application/json" \
      http://localhost:5000/api/drones/SENTINEL-01/land -d '{}' | jq .
    ```

The bridge logs should show receipt of each command.

## Pre WSL handoff verification

This section is designed to validate the Windows hosted Docker services before running PX4 and Gazebo in WSL.
It uses `.env.example` and does not require creation of a `.env` file.

1. Windows host verification
    ```bash
    docker compose --env-file .env.example up -d --build
    docker compose --env-file .env.example ps
    docker compose --env-file .env.example exec -T redis redis-cli ping

    curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5000/api/health

    set -a; source .env.example; set +a
    curl -s -o /dev/null -w '%{http_code}\n' -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" http://localhost:5000/api/health
    ```

2. WSL connectivity verification
    ```bash
    set -a; source .env.example; set +a
    curl -s -o /dev/null -w '%{http_code}\n' -H "X-API-Key: $LESNAR_OPERATOR_API_KEY" http://localhost:5000/api/health

    timeout 2 bash -c '</dev/tcp/127.0.0.1/6379' >/dev/null 2>&1 && echo redis-port-open || echo redis-port-closed
    ```

If WSL cannot reach Redis at 127.0.0.1, use the Windows only Docker mode and set the bridge `--redis-host` to `$WINDOWS_HOST`.

## Troubleshooting

1. Redis connection refused
    Confirm containers are running with `docker compose ps`.
    Confirm Redis responds with `docker compose exec -T redis redis-cli ping`.
    Confirm the bridge is pointed at the correct Redis host.
    If Docker is Windows only, use the `$WINDOWS_HOST` address.

2. Drone does not appear in the backend
    Confirm PX4 SITL is running and MAVLink is on UDP 14540.
    Confirm the bridge logs show successful connection to both Redis and MAVSDK.
    Confirm the backend lists drones with `GET /api/drones`.

## Project structure

```text
/
├── backend/             # Flask API and Redis bridge
├── frontend/            # React dashboard
├── training/            # PX4 and Gazebo bridge and training utilities
├── docs/                # Design documentation
├── shared/              # Shared artifacts mounted into containers
├── docker-compose.yml   # Compose stack
└── .env.example          # Example environment values for smoke tests
```

## Legacy components

Legacy AirSim related assets are under `legacy/`.
They are not part of the canonical runbook.

Copyright © 2026 Lesnar Autonomous Systems. All Rights Reserved.
