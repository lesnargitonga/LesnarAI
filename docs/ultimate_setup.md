# Ultimate Training & SITL Setup (No Compromises)

This document defines a production-grade, reproducible setup across simulation (PX4 SITL, Gazebo Harmonic, AirSim/Unreal) and training (PyTorch/Segmentation/RL), with auditability, privacy, and safety controls. Focus is reliability, low-latency, and clear version pinning.

## Hardware
- **Ubuntu Host (Primary):** Workstation or server (Ubuntu 22.04 LTS preferred for ecosystem compatibility)
- **CPU/GPU:** 16+ cores, 64GB RAM, NVIDIA RTX 4090/6000 ADA (24–48GB VRAM)
- **Storage:** 2TB NVMe SSD (datasets + logs); RAID-1 for audit DB optional
- **Network:** Wired Ethernet; optional second NIC for hardware HIL; low-latency switch
- **Windows Host (AirSim/Unreal):** Windows 11 Pro, 64GB RAM, NVIDIA RTX (for UE 5.3)

## OS & Drivers
- **Ubuntu 22.04 LTS (Jammy):** ROS 2 Humble + Gazebo Garden/Harmonic supported; better OSRF packages
- **NVIDIA Driver:** 550+ (data center or game ready)
- **CUDA:** 12.4; cuDNN 9; matching PyTorch wheels

## Simulation Stack
- **PX4 SITL (Ubuntu):**
  - Pin PX4 tag: `v1.14.3`
  - Targets: `gz` (Gazebo Garden/Harmonic) primary; `jmavsim` fallback
- **Gazebo:** OSRF apt repo on Ubuntu 22.04 with `gz-garden` or `gz-harmonic` packages
- **AirSim (Windows):** Unreal Engine 5.3; AirSim plugin; Blocks or custom level
- **ROS 2 (Ubuntu):** Humble; `microdds`/`cyclonedds`; optional MAVROS bridge

## Python & Tooling
- **PyTorch:** 2.2–2.9 with CUDA 12.x (Linux); CPU-only on Windows if needed
- **Torchvision:** 0.17–0.24 compatible with Torch
- **MAVSDK:** 1.6+ on both Ubuntu and Windows
- **SB3:** 2.7.x; Gymnasium 1.2.x
- **OpenCV, Albumentations, scikit-image:** for perception
- **TimescaleDB:** For audit logs, running in Docker (Linux)

## Networking & IPC
- **MAVLink:** UDP 14540 default; ensure firewall rules open between WSL/Windows and Ubuntu host
- **Time Sync:** `chrony` on Ubuntu; Windows time sync enabled
- **WSL 2 Bridging:** Prefer running collectors in the same OS as SITL; otherwise use WSL eth0 IP (e.g., `172.x.x.x:14540`)

## Privacy & Safety
- **Privacy Masking:** Enable face/PII blur in capture (`ai_modules/privacy.py`)
- **Loss-of-Link Failsafe:** Heartbeat and auto-land script in AirSim (`airsim/loss_of_link_failsafe.py`)
- **Compute Profiler:** Bound blind travel via latency (`scripts/compute_profiler.py`)
- **Audit Logging:** TimescaleDB writer integrated into autonomy; schema in `scripts/init_timescale.sql`

## Install — Ubuntu (SITL + Training)
```bash
# Base dev tools
sudo apt update
sudo apt install -y build-essential ninja-build ccache git zip python3-pip python3-venv python3-jinja2 python3-numpy default-jre chrony

# NVIDIA (if needed): install official drivers & CUDA from NVIDIA repo
# ... (follow NVIDIA instructions appropriate to hardware)

# PX4
git clone https://github.com/PX4/PX4-Autopilot
cd PX4-Autopilot
git checkout v1.14.3
git submodule update --init --recursive
make distclean

# Gazebo Garden/Harmonic (OSRF packages for Ubuntu 22.04)
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:gz/garden || true
sudo apt update
sudo apt install -y gz-garden || sudo apt install -y gz-harmonic || true

# Build SITL
make px4_sitl gz  # preferred
# If gz not available, fallback:
make px4_sitl jmavsim

# Python venv
python3 -m venv ~/.venvs/sitl
source ~/.venvs/sitl/bin/activate
pip install --upgrade pip
pip install mavsdk torch torchvision gymnasium stable-baselines3 opencv-python albumentations scikit-image tensorboard einops
```

## Install — Windows (AirSim)
```powershell
# Install Unreal Engine 5.3 (Epic Games Launcher)
# Clone AirSim and build plugin or use prebuilt binary
# Python venv (already in repo):
Set-Location "D:\docs\lesnar\Lesnar AI"
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r training\requirements.txt
```

## Run — PX4 SITL + Collector (Ubuntu)
```bash
# Start SITL (gz)
cd ~/PX4-Autopilot
make px4_sitl gz
# In another terminal, run collector writing to Windows share or local path
python3 "/mnt/d/docs/lesnar/Lesnar AI/training/px4_teacher_collect_adv.py" \
  --system 127.0.0.1:14540 \
  --waypoints "/mnt/d/docs/lesnar/Lesnar AI/training/px4_waypoints.json" \
  --out "/mnt/d/docs/lesnar/Lesnar AI/dataset/px4_teacher" \
  --duration 600 --hz 20 --alt 12 --base_speed 2.5 --max_speed 6 --yaw_rate_limit 60
```

## Run — PX4 SITL + Collector (Windows)
```powershell
# If SITL runs in WSL/Ubuntu, use the WSL eth0 IP (e.g., 172.20.x.x:14540)
Set-Location "D:\docs\lesnar\Lesnar AI"
& .\.venv\Scripts\python.exe .\training\px4_teacher_collect_adv.py --system 172.20.242.205:14540 --waypoints .\training\px4_waypoints.json --out .\dataset\px4_teacher --duration 600 --hz 20 --alt 12 --base_speed 2.5 --max_speed 6 --yaw_rate_limit 60
```

## Train — Student Policy (Windows)
```powershell
Set-Location "D:\docs\lesnar\Lesnar AI"
& .\.venv\Scripts\python.exe .\training\train_student_px4.py --data .\dataset\px4_teacher\telemetry_adv.csv --epochs 30 --bs 128 --out .\models\student_px4.pt
```

## Integrate — Autonomy & Evaluation
- **AirSim Hybrid:** Use `airsim/segmentation_autonomy.py` or VFH baseline; inject student action and compare against teacher
- **ROS 2 Bridge:** Optional MAVROS -> PX4 for richer sensor feeds; OBSTACLE_DISTANCE injection
- **TimescaleDB:** Start Docker compose for audit (`docker-compose.yml` updated)

## GPS-Denied Hardware (Reference)
- Apply EKF2 Optical Flow + Rangefinder params (`px4_config/gps_denied.params`)
- Validate hover stability; verify local position OK

## CI/CD & Reproducibility
- **Requirements Pinning:** `training/requirements.txt` kept narrow
- **Docker:** Optional containers for Gazebo/Timescale
- **Versioning:** Tag runs with Git SHA; store configs with artifacts
- **Telemetry:** Capture 10–20 Hz logs with actions for forensics

## Troubleshooting
- **WSL UDP:** Prefer collector in same OS as SITL to avoid NAT quirks
- **gz Packages:** If unavailable on Ubuntu 24.04 (`noble`), use Ubuntu 22.04 or JMAVSim
- **Torch CUDA:** Match CUDA version and wheel; use `pip install torch==<version>+cu121` as needed

