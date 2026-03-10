# Lesnar AI – Training Pipeline

> **Canonical workflow: PX4 + Gazebo in WSL2** (see root `README.md` for full startup).  
> AirSim-based pipelines are **legacy** — assets moved to `legacy/`. Do not use AirSim commands for the submission.

## Primary Workflow — PX4 + Gazebo (current)

### 1) Setup WSL venv

```bash
cd ~/workspace/LesnarAI
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -U pip
pip install mavsdk numpy redis async-timeout
```

### 2) Start Gazebo with obstacle world

```bash
cd ~/workspace/LesnarAI
gz sim -v4 -r obstacles.sdf
```

World: **85 obstacles** — 25 skyscrapers, 50 spires, 10 trees.

### 3) Start PX4 SITL (connect to running Gazebo)

```bash
cd ~/PX4-Autopilot
export PX4_GZ_MODEL="x500"
export PX4_GZ_WORLD="obstacles"
PX4_GZ_STANDALONE=1 make px4_sitl gz_x500
```

Expected: `INFO [commander] Ready for takeoff!`

### 4) Run the bridge / data collector

**Autonomous data collection** (default — drone flies A* path and writes CSV):

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

Output:
- `dataset/px4_teacher/telemetry_*.csv` — pose, velocity, heading, obstacle detections
- `logs/seg_diag_*.csv` — lidar-derived obstacle events per cycle

**App-controlled bridge** (operator drives via web UI — no autonomous flight):

```bash
python3 training/px4_teacher_collect_gz.py --duration 0 --mavsdk-server auto --bridge_only
```

> **Important:** `--bridge_only` produces **zero-byte CSVs** because the drone never takes off on its own. Only use it for live operator demos.

### 5) Verify data collection is working

```bash
wc -l dataset/px4_teacher/telemetry_*.csv
tail -3 dataset/px4_teacher/telemetry_*.csv
```

Expect row count to increment every few seconds.

---

## Legacy — AirSim-Based Pipeline (not used for submission)

NOTE: the AirSim-based pipeline is legacy. AirSim assets/env were moved under `legacy/`.
- Legacy AirSim code: `legacy/airsim/`
- Legacy AirSim Python env: `legacy/airsim-env/`

### Dataset Preprocessing (AirSim/legacy)

Unify external datasets under a common format (RGB + Depth + Pose):

```powershell
python training/preprocess_datasets.py --roots D:\datasets\TUM_RGBD D:\datasets\KITTI --out D:\datasets\unified --width 640 --height 360 --fps 10 --src_fps 30
```

### Collect Synthetic Data from AirSim (legacy)

```powershell
python training/collect_airsim_dataset.py --out D:\datasets\airsim_synth --duration 120 --hz 5
```

### Train Segmentation (legacy)

```powershell
python training/train_segmentation.py --data D:\datasets\unified\KITTI\seq_00 --epochs 10 --bs 4 --lr 1e-3 --out models/seg_unet.pt
```

### Supervised Navigation (legacy)

```powershell
python training/train_navigation.py --data D:\datasets\airsim_synth --epochs 10 --bs 8 --seq_len 4 --out models/vision_nav.pt
```

### Reinforcement Learning in AirSim (legacy)

Start AirSim, then train PPO on the Gym environment:

```powershell
python training/train_rl.py --steps 20000 --out models/ppo_airsim
```

## 7) Integrate with Autonomy

Use your trained policy to compute actions from live frames and send with AirSim’s `moveByVelocityAsync`. See `airsim/vfh_avoid_multi.py` for a robust reactive baseline; you can hybridize: policy suggests action, VFH adds safety.

## 8) Tips

- Start with low camera resolutions and 5–10 Hz loops for stability.
- Use `training/preprocess_datasets.py` to normalize all inputs.
- Keep training logs in TensorBoard (`tensorboard --logdir runs`).# AirSim Segmentation Training (PyTorch)

## AirSim Segmentation Training (PyTorch) (Legacy)

End-to-end steps to train a UNet model from AirSim data and use it in autonomy.

## 1) Configure segmentation IDs in AirSim

In VS Code terminal (Unreal must be in Play):

```powershell
Set-Location "D:\docs\lesnar\Lesnar AI"
.\legacy\airsim-env\Scripts\python.exe .\legacy\airsim\setup_segmentation_ids.py
```

This sets free space (ground/road) to ID 0 and obstacles to ID 1.

## 2) Collect a dataset

```powershell
# Collect train split (moving)
.\legacy\airsim-env\Scripts\python.exe .\training\collect_airsim_dataset.py --split train --count 1000 --move --sleep 0.05

# Collect val split (stationary or slower)
.\legacy\airsim-env\Scripts\python.exe .\training\collect_airsim_dataset.py --split val --count 200 --sleep 0.1
```

This creates:
```
dataset/
  train/images/*.png
  train/masks/*.png  (# IDs: 0=free, 1=obstacle)
  val/images/*.png
  val/masks/*.png
```

## 3) Train UNet (GPU if available)

```powershell
.\legacy\airsim-env\Scripts\python.exe .\training\pytorch_unet.py --data .\dataset --img_size 256 256 --batch 8 --epochs 20 --classes 1 --out .\runs\unet_airsim --base 32
```

Artifacts are saved under `runs\unet_airsim\`:
- `last.pt`, `best.pt`: PyTorch state_dict
- `model_ts.pt`: TorchScript export
- `tb/`: TensorBoard logs

Optional: launch TensorBoard
```powershell
.\legacy\airsim-env\Scripts\python.exe -m tensorboard --logdir .\runs\unet_airsim\tb
```

## 4) Use the trained model in autonomy

Point the autonomy or demo to your trained weights:

```powershell
# Demo overlay
.\legacy\airsim-env\Scripts\python.exe .\legacy\airsim\segmentation_demo.py --model .\runs\unet_airsim\best.pt --img_size 256 256 --invert_mask --avoid --auto_move

# Full autonomy
.\legacy\airsim-env\Scripts\python.exe .\legacy\airsim\segmentation_autonomy.py --model .\runs\unet_airsim\best.pt --img_size 256 256 --invert_mask --log_csv .\logs\seg_diag.csv
```

If the overlay looks inverted (free vs obstacle), keep `--invert_mask` on. If your masks are already 1=obstacle, you can omit it.

## Tips
- If masks look noisy, increase dataset size and vary viewpoints.
- You can bump `--img_size` to 384 or 512 for better detail (ensure VRAM/RAM is sufficient).
- If frames are too similar, increase movement patterns in the collector (strafe/yaw) or collect in different areas.

## 9) PX4 Teacher Brain (SITL – Advanced)

Collect high-quality demonstrations from PX4 SITL using MAVSDK Offboard and train a student policy.

### Collect advanced teacher demos
Requires PX4 SITL running (UDP:14540) and `mavsdk` installed in your Python env.

```
# Start PX4 SITL in WSL
git clone https://github.com/PX4/PX4-Autopilot
cd PX4-Autopilot
make px4_sitl gazebo

# Collect demos (Windows PowerShell)
& .\.venv\Scripts\python.exe .\training\px4_teacher_collect_adv.py --system 127.0.0.1:14540 --waypoints .\training\px4_waypoints.json --out .\dataset\px4_teacher --duration 300 --hz 20 --alt 10 --base_speed 2 --max_speed 5 --yaw_rate_limit 45
```

### Train student from PX4 demos

```
& .\.venv\Scripts\python.exe .\training\train_student_px4.py --data .\dataset\px4_teacher\telemetry_adv.csv --epochs 20 --bs 128 --out .\models\student_px4.pt
```

For GPS-denied validation on hardware, apply EKF2 Optical Flow + Rangefinder params (see `px4_config/gps_denied.params`) and test hover stability.
