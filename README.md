# Operation Sentinel

## Overview
Operation Sentinel is a local, offline-capable drone autonomy and command control stack. 
It is designed for simulation in PX4 SITL with Gazebo Harmonic.

### 🛑 CRITICAL HACKATHON DIRECTIVE (MARCH 2026)
**Do not run this via Windows Mounts (`/mnt/d/...`)**. You must open this repository using the **"WSL: Ubuntu" Remote extension in VS Code**. If you use PowerShell, Gazebo will lag and the UI will fail to bind. All terminals mentioned below MUST be native WSL bash terminals.

**Canonical native location:** `~/workspace/LesnarAI`

**Verify before running demo commands:**
```bash
pwd && realpath .
```
Both lines must resolve under `/home/...` and **not** `/mnt/...`.

---

## ⚡ Presentation Day Quick Start (10 Minutes)

Run these in order from WSL at `~/workspace/LesnarAI`.

### 1) Bootstrap secure runtime files
```bash
cd ~/workspace/LesnarAI
python3 scripts/bootstrap_secure_deployment.py
python3 scripts/validate_secure_deployment.py
```

### 2) Start backend services
```bash
docker compose --env-file .env.secure up -d --build
```

Local fallback: if `.env.secure` has not been generated yet, `docker compose up -d --build` now uses safe local development defaults for auth/session secrets and telemetry timing. For presentation or shared environments, continue to use `.env.secure`.

### 3) Start frontend
```bash
cd ~/workspace/LesnarAI/frontend
npm start
```

### 4) Login and verify health
```bash
cd ~/workspace/LesnarAI
export LESNAR_USER="lesnar"
export LESNAR_PASS="lesnar1234"
export SESSION_HEADER="$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")"
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/health | jq .status
```

### 4.1) Run command preflight (recommended only after live simulation/teacher is running)
```bash
cd ~/workspace/LesnarAI
./scripts/preflight_control_check.sh --username "$LESNAR_USER" --password "$LESNAR_PASS"
```
This validates auth, backend health, active drone presence, and telemetry freshness.
If PX4 + Gazebo + teacher are not running yet, this check is expected to fail.

### 5) Open demo URLs
- Frontend: http://localhost:3000 (only after `cd ~/workspace/LesnarAI/frontend && npm start`)
- Backend health: do not open directly in browser in secure mode; verify with authenticated curl instead:

```bash
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/health | jq .
```
- Adminer: http://localhost:8080

### 6) Optional live simulation
```bash
cd ~/workspace/LesnarAI
gz sim -v4 -r obstacles.sdf &
sleep 10
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

In another WSL terminal:
```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate
mkdir -p dataset/px4_teacher logs
python3 training/px4_teacher_collect_gz.py --duration 0 --mavsdk-server auto --hz 5
```

**Two bridge modes — pick the right one:**

| Mode | Command | Use when |
|------|---------|----------|
| **Autonomous data collection** | *(no flag)* — default | Recording training data; drone flies its own A* path through `obstacles.sdf` |
| **App-controlled bridge** | `--bridge_only` | Live operator demo where the app sends arm/takeoff/goto/land commands |

> **Do not mix them up.** Running `--bridge_only` for a data-collection session produces **zero-byte CSVs** because the bridge never takes off. Running without it during a live operator demo means the bridge overrides operator commands.

---

## 🚀 The Native WSL Demo Playbook (A-Z)

This is the current reliable sequence for March 2026.

### A) Terminal 1 — Backend and auth baseline
```bash
cd ~/workspace/LesnarAI
python3 scripts/bootstrap_secure_deployment.py
python3 scripts/validate_secure_deployment.py || true
docker compose --env-file .env.secure up -d --build

export LESNAR_USER="lesnar"
export LESNAR_PASS="lesnar1234"
export SESSION_HEADER="$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")"
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/health | jq .status
```

### B) Terminal 2 — Gazebo (server/headless recommended)
```bash
cd ~/workspace/LesnarAI
gz sim -s -r obstacles.sdf
```

If you want GUI mode instead, use `gz sim -v4 -r obstacles.sdf`.

### C) Terminal 3 — PX4 SITL
```bash
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
export PX4_GZ_WORLD="obstacles"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

Expected: `INFO [commander] Ready for takeoff!`

### D) Terminal 4 — Teacher bridge

**For data collection (autonomous flight):**
```bash
cd ~/workspace/LesnarAI
source .venv-wsl/bin/activate
mkdir -p dataset/px4_teacher logs
python3 training/px4_teacher_collect_gz.py --duration 0 --mavsdk-server auto --hz 5 --alt 12 --base_speed 1.2 --max_speed 2.5
```
Drone takes off autonomously, navigates the obstacle world with A*, and records telemetry to `dataset/px4_teacher/telemetry_*.csv`.

**For live app-controlled demo (operator drives the drone):**
```bash
python3 training/px4_teacher_collect_gz.py --duration 0 --mavsdk-server auto --hz 5 --bridge_only
```
Bridge stays passive; all commands (arm/takeoff/goto/land) come from the web app.

Expected logs: `Redis CONNECTED`, then either `FALCON` metrics (autonomous) or `bridge_only: waiting for app commands`.

### E) Terminal 1 — Preflight gate before any command
```bash
cd ~/workspace/LesnarAI
./scripts/preflight_control_check.sh --username "$LESNAR_USER" --password "$LESNAR_PASS"
```

Only send control commands after preflight reports ready.

### F) Terminal 1 — Confirm active drone
```bash
SESSION_HEADER="$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")"
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/drones | jq .
```

Expected: `count >= 1`, `SENTINEL-01` present, and the live PX4 bridge drone reports `"source": "external"`.

### G) App control model
Once the live bridge drone appears as `source: external`, normal operator control is handled from the web app:
- arm / disarm
- takeoff / land
- goto / waypoint navigation
- mission start / pause / resume / stop
- live map tracking
- analytics and log export

Training is separate from operator control. Start training and data-collection workflows from the terminal, while using the app for flight operations, tracking, analysis, and exports.

### H) Terminal 1 — Control commands
```bash
# Takeoff
curl -s -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" \
    -d '{"altitude":10}' \
    http://localhost:5000/api/drones/SENTINEL-01/takeoff | jq .

# Land
curl -s -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" \
    -d '{}' \
    http://localhost:5000/api/drones/SENTINEL-01/land | jq .
```

### H) Fast recovery if things desync
```bash
pkill -f "px4_sitl|gz sim|gz-sim|px4_teacher_collect_gz.py|mavsdk_server" || true
docker compose --env-file .env.secure restart backend
```

Then restart from step B.

---

## ✅ Systematic Verification Checklist

Run these in Terminal 1 after startup:

```bash
cd ~/workspace/LesnarAI
export LESNAR_USER="lesnar"
export LESNAR_PASS="lesnar1234"
export SESSION_HEADER="$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")"

# Backend auth/health
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/health | jq .status

# Active drone feed
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/drones | jq .

# Preflight before commands
./scripts/preflight_control_check.sh --username "$LESNAR_USER" --password "$LESNAR_PASS"
```

Expected:
- health returns `ok`
- `/api/drones` shows `count: 1` only after PX4 + teacher are actually running
- preflight ends with ready/success

---

## 🧯 If the state looks wrong

### Case 1: Drone appears before you intended to start simulation
That means `gz sim`, `px4_sitl`, or `px4_teacher_collect_gz.py` is still running in the background.

Check:
```bash
pgrep -af "px4_teacher_collect_gz.py|px4_sitl|gz sim|gz-sim|mavsdk_server" || true
```

Stop all simulation-side processes:
```bash
pkill -f "px4_teacher_collect_gz.py|px4_sitl|gz sim|gz-sim|mavsdk_server" || true
sleep 6
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/drones | jq .
```

Expected: `count: 0`

### Case 2: Frontend shows old 401 or stale command errors
- Refresh the browser once.
- Re-login if required.
- Re-run preflight before trying commands again.

### Case 3: Backend is healthy but `/api/drones` is empty
- PX4 and teacher are not fully connected yet, or telemetry is stale.
- Keep the teacher running and wait for preflight to pass.

### Case 4: Mission Control shows deployment unavailable
- This should no longer happen for the live PX4/Gazebo bridge drone in the current March 2026 flow.
- If it does happen, the likely causes are stale frontend state, an old backend container, or an old bridge process still running without the updated external mission support.
- Verify the drone reports `source: external`, then restart backend + bridge if Mission Control still appears locked.

---

## 🛑 Clean Shutdown

Use this when you are done testing or before a fresh restart:

```bash
pkill -f "px4_teacher_collect_gz.py|px4_sitl|gz sim|gz-sim|mavsdk_server" || true
cd ~/workspace/LesnarAI
docker compose --env-file .env.secure down
```

---

## 🌐 All URLs for Presentation

| Service | URL | Purpose |
|---------|-----|---------|
| **Backend API** | http://localhost:5000 | REST API base |
| **API Health** | http://localhost:5000/api/health | Use authenticated curl only in secure mode |
| **API Drones** | http://localhost:5000/api/drones | Use authenticated curl only |
| **Adminer (Database)** | http://localhost:8080 | View telemetry in TimescaleDB |
| **Frontend Dashboard** | http://localhost:3000 | React UI (if running) |

---

## 📦 Optional: Frontend Dashboard

```bash
# WSL Terminal (separate from others)
cd ~/workspace/LesnarAI/frontend
npm start
```

Then open: **http://localhost:3000**

---

## 🎯 Quick Reference

**Session Header:** `$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")`
**Database Password:** `POSTGRES_PASSWORD` from `.env.secure`
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
mkdir -p ~/workspace/LesnarAI
rsync -a --delete "/mnt/<drive>/path/to/repo/" ~/workspace/LesnarAI/
cd ~/workspace/LesnarAI
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
    For real deployments, generate secure envs and frontend runtime env files:
    ```bash
    python3 scripts/bootstrap_secure_deployment.py
    python3 scripts/validate_secure_deployment.py
    ```
    Only use `.env.example` for isolated non-sensitive smoke tests.

2. Start services
    ```bash
    docker compose --env-file .env.secure up -d --build
    docker compose --env-file .env.secure ps
    ```

    For isolated local development only, `docker compose up -d --build` also works now because `docker-compose.yml` provides secure local fallback values for required backend env vars.

3. Default endpoints
    Backend API is `http://localhost:5000`.
    Adminer is `http://localhost:8080`.

4. Keys and configuration
    The backend is fail-closed by default.
    Session auth is the primary control path and browser API-key fallback is disabled by default.
    Set strong values for `LESNAR_ADMIN_API_KEY` and `LESNAR_OPERATOR_API_KEY` only for legacy CLI fallback or automation that still depends on them.
    Set `LESNAR_AUDIT_CHAIN_KEY` and `LESNAR_DATASET_SIGN_KEY` for signed audit/data integrity controls.
    Restrict web origins via `LESNAR_CORS_ORIGINS`.
    For secure operation, populate `LESNAR_AUTH_USERS_JSON`, `LESNAR_OPERATIONAL_BOUNDARY`, and local tile settings before use.

## Frontend

1. Generate frontend runtime env
    ```bash
    python3 scripts/bootstrap_secure_deployment.py --force
    ```
    This writes both `frontend/.env.local.secure` and the runtime file `frontend/.env.local`.

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
    cp ~/workspace/LesnarAI/obstacles.sdf ~/PX4-Autopilot/Tools/simulation/gz/worlds/obstacles.sdf
    ```

3. **Start Gazebo with obstacles world FIRST**
    ```bash
    cd ~/workspace/LesnarAI
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
    export PX4_GZ_WORLD="obstacles"
    PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
    ```

The x500 drone will spawn in Gazebo among the obstacles. PX4 exposes MAVLink on UDP port 14540 by default.

**Note:** The two-step startup (Gazebo first, then PX4) is required because the obstacles world is large (85 obstacles) and needs time to load before PX4 connects.

## Bridge process

1. Create a Python virtual environment
    ```bash
    cd ~/workspace/LesnarAI
    python3 -m venv .venv-wsl
    source .venv-wsl/bin/activate
    pip install -U pip
    pip install mavsdk numpy redis async-timeout
    ```

2. Start the bridge process

    **Autonomous data collection mode** (default — records training CSV):
    ```bash
    mkdir -p dataset/px4_teacher logs
    python3 training/px4_teacher_collect_gz.py \
      --drone-id SENTINEL-01 \
      --redis-host 127.0.0.1 \
      --redis-port 6379 \
      --mavsdk-server auto \
      --hz 5 --alt 12 --base_speed 1.2 --max_speed 2.5
    ```

    **App-controlled bridge mode** (operator drives via web app):
    ```bash
    python3 training/px4_teacher_collect_gz.py \
      --drone-id SENTINEL-01 \
      --redis-host 127.0.0.1 \
      --redis-port 6379 \
      --mavsdk-server auto \
      --bridge_only
    ```

If Docker runs only on Windows, replace `--redis-host 127.0.0.1` with `--redis-host $WINDOWS_HOST`.

## Training workflow

Training is started from the terminal, not from the app UI.

Use the app for:
- live control
- mission planning/execution
- tracking
- analytics
- log export

Use the terminal for:
- dataset collection
- model training
- RL / BC experiments
- TensorBoard or offline analysis runs

Examples are documented in [training/README.md](training/README.md).

## Smoke test

Run these from WSL unless you are using the Windows only Docker mode.

1. Confirm containers
    ```bash
        docker compose --env-file .env.secure up -d --build
        docker compose --env-file .env.secure ps
        docker compose --env-file .env.secure exec -T redis redis-cli ping
    ```

2. Confirm backend authentication
    ```bash
        export LESNAR_USER="lesnar"
        export LESNAR_PASS="lesnar1234"
        export SESSION_HEADER="$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")"
        curl -s -H "$SESSION_HEADER" http://localhost:5000/api/health | jq .status
    ```

3. Confirm the bridge appears as a drone
    ```bash
        curl -s -H "$SESSION_HEADER" http://localhost:5000/api/drones | jq '.drones[] | {drone_id, source, mode}'
    ```

Expected live result includes `"drone_id": "SENTINEL-01"` and `"source": "external"`.

4. Confirm Mission Control support for the live drone
    - Open the app and select `SENTINEL-01`
    - Create a waypoint plan in Mission Control
    - Start, pause, resume, and stop the mission from the app
    - Verify `/api/missions/active` reflects the current state

5. Confirm command propagation
    ```bash
        curl -s -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" \
      http://localhost:5000/api/drones/SENTINEL-01/takeoff -d '{"altitude":10}' | jq .

        curl -s -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" \
      http://localhost:5000/api/drones/SENTINEL-01/goto -d '{"latitude":40.7129,"longitude":-74.0061,"altitude":10}' | jq .

        curl -s -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" \
      http://localhost:5000/api/drones/SENTINEL-01/land -d '{}' | jq .
    ```

The bridge logs should show receipt of each command.

6. Security integrity checks
    ```bash
    set -a; source .env.secure; set +a
    python3 scripts/security_posture_check.py
    python3 scripts/verify_audit_chain.py
    python3 scripts/dataset_integrity.py create --dataset-root dataset --manifest docs/security/dataset_manifest.json
    python3 scripts/dataset_integrity.py verify --dataset-root dataset --manifest docs/security/dataset_manifest.json
    ```

7. Security architecture endpoint (admin only)
    ```bash
    curl -s -H "$SESSION_HEADER" http://localhost:5000/api/security/status | jq .
    ```
    Returns the full security posture: auth method, brute-force config, response headers, CORS, audit chain, user counts by role.

8. User management (admin only) — add/remove operators via the web app:
   - Go to **Settings → Operator Access Control**
   - Or use the API directly:
    ```bash
    # List users
    curl -s -H "$SESSION_HEADER" http://localhost:5000/api/auth/users | jq .
    # Create user
    curl -s -X POST -H "$SESSION_HEADER" -H "Content-Type: application/json" \
      -d '{"username":"newop","role":"operator","password":"StrongPass99","display_name":"New Operator"}' \
      http://localhost:5000/api/auth/users
    # Update role
    curl -s -X PUT -H "$SESSION_HEADER" -H "Content-Type: application/json" \
      -d '{"role":"viewer"}' http://localhost:5000/api/auth/users/newop
    # Delete user
    curl -s -X DELETE -H "$SESSION_HEADER" http://localhost:5000/api/auth/users/newop
    ```

## Pre WSL handoff verification

This section is designed to validate the Windows hosted Docker services before running PX4 and Gazebo in WSL.
For secure operation, use `.env.secure` instead of `.env.example`.

1. Windows host verification
    ```bash
    docker compose --env-file .env.secure up -d --build
    docker compose --env-file .env.secure ps
    docker compose --env-file .env.secure exec -T redis redis-cli ping

    curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5000/api/health

    export LESNAR_USER="lesnar"
    export LESNAR_PASS="lesnar1234"
    export SESSION_HEADER="$(python3 scripts/request_session_token.py --username "$LESNAR_USER" --password "$LESNAR_PASS")"
    curl -s -o /dev/null -w '%{http_code}\n' -H "$SESSION_HEADER" http://localhost:5000/api/health
    ```

2. WSL connectivity verification
    ```bash
    curl -s -o /dev/null -w '%{http_code}\n' -H "$SESSION_HEADER" http://localhost:5000/api/health

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

3. Mission deployment button is disabled for the live drone
    This is no longer expected in the current live PX4 bridge flow.
    Confirm the backend and bridge were restarted after the March 2026 external mission-control update.
    Confirm the drone appears from `/api/drones` as `source: external`.
    If needed, restart the bridge in `--bridge_only` mode and reload the frontend.

## Project structure

```text
/
├── backend/             # Flask API, Redis bridge, auth, mission control
├── frontend/            # React dashboard (port 3000)
├── training/            # PX4+Gazebo bridge + legacy AirSim training utilities
│   └── px4_teacher_collect_gz.py  # Primary bridge/data-collector (use this)
├── rl/                  # RL scripts (legacy AirSim-based; see rl/README.md)
├── dataset/px4_teacher/ # Telemetry CSV output from autonomous data collection
├── logs/                # seg_diag_*.csv from obstacle/segmentation diagnostics
├── obstacles.sdf        # Gazebo world (85 obstacles – copy to PX4 worlds dir)
├── auth_users.json      # User accounts (PBKDF2-SHA256 hashed passwords)
├── docs/                # Design documentation and architecture diagrams
├── shared/              # Shared artifacts mounted into containers
├── docker-compose.yml   # Compose stack (backend/redis/timescaledb/adminer)
└── .env.secure          # Secure runtime environment values (generate with bootstrap script)
```

## Security Architecture

The system is hardened for demonstration and production use:

| Layer | Implementation |
|---|---|
| Authentication | PBKDF2-SHA256 (390k iterations), `itsdangerous` signed tokens, DB-backed revocation |
| Session TTL | 30 minutes; revoked immediately on password change |
| Brute-force protection | 5 failed attempts in 60s → 5-minute lockout per IP+username |
| Response headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store` |
| Role hierarchy | `viewer` < `operator` < `admin` — enforced per route |
| User management | Full CRUD via API (`/api/auth/users`) and frontend Settings UI (admin only) |
| Error sanitisation | Raw exceptions never exposed to client |
| Audit log | Append-only event log in TimescaleDB |
| Rate limiting | 20 req/min on login (flask-limiter) |

View live security posture:
```bash
curl -s -H "$SESSION_HEADER" http://localhost:5000/api/security/status | jq .
```

Copyright © 2026 Lesnar Autonomous Systems. All Rights Reserved.
