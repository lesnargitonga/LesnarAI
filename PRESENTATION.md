# Operation Sentinel - Presentation Guide

## 🎯 Presentation Overview

**What You're Demonstrating:**
A fully autonomous drone system with:
- Real-time obstacle avoidance using simulated LiDAR
- Hybrid architecture (PX4 for flight control + AI for mission planning)
- Complete data pipeline (Gazebo → PX4 → Bridge → Redis → TimescaleDB)
- RESTful API for command & control
- Live telemetry visualization

---

## 🚀 Pre-Presentation Setup (15 minutes before)

### 1. Start Backend Services
```bash
# Windows PowerShell or WSL
cd "d:\docs\lesnar\Lesnar AI"
docker compose --env-file .env.example down -v
docker compose --env-file .env.example up -d
```

**Wait for health check:**
```bash
curl -H "X-API-Key: example-operator-key" http://localhost:5000/api/health
# Should return: {"status":"ok"}
```

### 2. Start Gazebo with Obstacles (WSL Terminal 1)
```bash
cd ~/lesnar/LesnarAI
gz sim -v4 -r obstacles.sdf &
```

**⏱️ Wait 10-15 seconds** for Gazebo GUI to fully load showing:
- 25 colored skyscrapers (80-150m tall)
- 50 red spires (200m tall)  
- 10 green trees (ground level)

### 3. Start PX4 (WSL Terminal 1 - same as Gazebo)
```bash
sleep 10
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

**✅ Success indicator:** Console shows `INFO [commander] Ready for takeoff!`

### 4. Start Bridge Script (WSL Terminal 2 - NEW)
```bash
cd ~/lesnar/LesnarAI
source .venv-wsl/bin/activate
mkdir -p dataset/px4_teacher
python3 training/px4_teacher_collect_gz.py --duration 300
```

**✅ Success indicators:**
```
[INFO] --> Redis connected (Bridge Established) at 127.0.0.1:6379
[INFO] --> Connected!
[INFO] --> Arming...
```

### 5. Open Adminer (Browser)
Navigate to `http://localhost:8080` and login:
- **Server:** `timescaledb`
- **Username:** `lesnar`
- **Password:** `example-password`
- **Database:** `lesnar`

**✅ Verify:** You should see tables: `drones`, `flight_log`, `command_logs`, `events`

---

## 🎤 Presentation Flow

### Part 1: System Architecture (3 minutes)

**Show this diagram:**

```
┌─────────────────────────────────────────────────────────┐
│                    WSL2 (Ubuntu)                        │
│                                                         │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │   Gazebo     │  │  PX4 SITL   │  │    Bridge    │  │
│  │  (Physics)   │◄─┤  (Autopilot)│◄─┤   Script     │  │
│  │  85 obstacles│  │   MAVLink   │  │  Simulated   │  │
│  └──────────────┘  └─────────────┘  │   LiDAR      │  │
│                                     └──────┬───────┘  │
│                                            │ Redis    │
└────────────────────────────────────────────┼──────────┘
                                             │
┌────────────────────────────────────────────┼──────────┐
│              Docker (Backend)              │          │
│                                            ▼          │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────┐ │
│  │  Redis   │◄─┤ Flask API  │◄─┤  TimescaleDB     │ │
│  │ (Pub/Sub)│  │  (REST)    │  │ (Time-series DB) │ │
│  └──────────┘  └────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Talking Points:**
1. **Gazebo Harmonic**: Physics simulation with 85 obstacles
2. **PX4 SITL**: Industry-standard autopilot (EKF2, attitude control, 250Hz)
3. **Bridge Script**: 
   - Parses `obstacles.sdf` for perfect obstacle knowledge
   - Simulates 360° LiDAR (72 rays, 20m range)
   - Publishes telemetry to Redis every cycle
4. **Backend**: Flask API with TimescaleDB for time-series telemetry
5. **Redis**: Real-time pub/sub for commands and telemetry

### Part 2: Live Demonstration (5 minutes)

#### Demo 1: Show Gazebo Environment
**Action:** Rotate Gazebo camera to show obstacles
**Say:** "Our simulation environment contains 85 obstacles - skyscrapers, spires, and trees. The drone must navigate through this complex urban environment."

#### Demo 2: Show Database (Adminer)
**Action:** 
1. Click on `drones` table → Show data
2. Click on `flight_log` table → Show real-time telemetry

**Say:** "All telemetry is stored in TimescaleDB - a time-series database optimized for IoT and sensor data. You can see position, velocity, heading updating in real-time."

#### Demo 3: Check Drone Status
```bash
curl -H "X-API-Key: example-operator-key" http://localhost:5000/api/drones | jq
```

**Say:** "Our REST API provides programmatic access to all drone operations. Here we see SENTINEL-01 is armed and ready."

#### Demo 4: Command Takeoff
```bash
curl -X POST -H "X-API-Key: example-operator-key" \
  -H "Content-Type: application/json" \
  -d '{"altitude": 10}' \
  http://localhost:5000/api/drones/SENTINEL-01/takeoff
```

**Action:** Watch Gazebo - drone should takeoff to 10m
**Say:** "Commands flow through Redis pub/sub to the bridge, which translates them to MAVLink commands for PX4."

#### Demo 5: Navigate Through Obstacles
```bash
curl -X POST -H "X-API-Key: example-operator-key" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 47.3977, "longitude": 8.5456, "altitude": 50}' \
  http://localhost:5000/api/drones/SENTINEL-01/goto
```

**Action:** Watch Gazebo - drone navigates using A* pathfinding
**Say:** "The bridge uses A* pathfinding with simulated LiDAR to avoid obstacles. This demonstrates the hybrid architecture - PX4 handles low-level control, while our AI handles mission planning."

#### Demo 6: Show Telemetry Updates
**Action:** Refresh `flight_log` table in Adminer
**Say:** "Every position update, velocity change, and sensor reading is logged for analysis and training data collection."

#### Demo 7: Land
```bash
curl -X POST -H "X-API-Key: example-operator-key" \
  http://localhost:5000/api/drones/SENTINEL-01/land
```

**Action:** Watch drone land in Gazebo

### Part 3: Technical Deep Dive (2 minutes)

**Key Technical Points:**

1. **Simulated LiDAR (God-Mode)**
   - Parses `obstacles.sdf` XML to extract exact obstacle positions
   - Ray-casts 72 beams in 360° to detect obstacles
   - Provides perfect, noise-free training data
   - Why? Gazebo's LiDAR sensor can be unreliable; this gives clean data for RL training

2. **Hybrid Architecture**
   - **Reflex Layer (PX4)**: Deterministic flight control, EKF2, 250Hz+
   - **Mission Layer (Bridge/AI)**: Stochastic planning, obstacle avoidance, 10-50Hz
   - Decoupling allows each layer to operate at optimal frequency

3. **Data Pipeline**
   - Telemetry: PX4 → MAVSDK → Bridge → Redis → Backend → TimescaleDB
   - Commands: API → Redis → Bridge → MAVSDK → PX4
   - All data persisted for analysis and model training

4. **Offline Capability**
   - No cloud dependency in operational loop
   - All processing local (WSL2 + Docker)
   - Data can be synced later for analysis

---

## 📊 Key Metrics to Highlight

- **85 obstacles** in simulation environment
- **360° LiDAR** coverage (72 rays, 20m range)
- **Real-time telemetry** (20Hz update rate)
- **Sub-second command latency** (API → Drone)
- **Time-series database** for historical analysis

---

## 🛠️ Troubleshooting During Presentation

### If Gazebo doesn't show obstacles:
```bash
# Kill and restart
sudo killall -9 gz ruby px4
cd ~/lesnar/LesnarAI
gz sim -v4 -r obstacles.sdf &
```

### If PX4 won't connect:
```bash
# Ensure Gazebo is fully loaded (wait 15 seconds)
# Then restart PX4
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

### If bridge script fails:
```bash
# Check Redis connectivity
docker compose exec redis redis-cli ping
# Should return: PONG

# Restart bridge
cd ~/lesnar/LesnarAI
source .venv-wsl/bin/activate
python3 training/px4_teacher_collect_gz.py --duration 300
```

### If Adminer won't login:
```bash
# Reset Docker with fresh volumes
docker compose --env-file .env.example down -v
docker compose --env-file .env.example up -d
# Wait 10 seconds, then try login again
```

---

## 💡 Q&A Preparation

**Q: Why simulate LiDAR instead of using Gazebo's sensor?**
A: Gazebo's LiDAR can be unreliable (stuck readings, noise). Our simulated LiDAR provides perfect ground truth for training, then we can add realistic noise later for robustness testing.

**Q: How does this scale to multiple drones?**
A: The architecture supports multiple drones - each gets a unique ID, publishes to separate Redis channels, and the backend tracks them independently. TimescaleDB handles high-throughput time-series data efficiently.

**Q: What about real hardware?**
A: PX4 runs on real flight controllers (Pixhawk, etc.). The bridge script would connect to real hardware via the same MAVLink protocol. Only the simulation (Gazebo) would be replaced with real sensors.

**Q: How do you train the AI?**
A: The bridge collects expert demonstrations (A* pathfinding) and saves to CSV. This data trains a PPO agent (Proximal Policy Optimization) to learn obstacle avoidance from the expert's behavior.

**Q: What's the latency?**
A: Command → PX4 is typically <100ms. Telemetry publishes at 20Hz. The bottleneck is usually the AI inference (10-50Hz depending on model complexity).

---

## ✅ Post-Presentation Cleanup

```bash
# Stop all processes
sudo killall -9 gz ruby px4
docker compose down

# Optional: Clean volumes
docker compose down -v
```

---

## 📁 Files Reference

- **Architecture**: `docs/architecture.md`
- **Obstacles World**: `obstacles.sdf` (85 obstacles defined)
- **Bridge Script**: `training/px4_teacher_collect_gz.py`
- **Backend API**: `backend/app.py`
- **Docker Setup**: `docker-compose.yml`
- **Environment**: `.env.example`

---

**Good luck with your presentation! 🚁**
