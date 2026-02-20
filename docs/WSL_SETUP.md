# WSL Setup Guide

The Windows environment (PowerShell) and WSL (Ubuntu) are separate. Your Windows Python environment (`.venv`) **does not work** inside WSL. You must create a new one.

## 1. Setup Python in WSL

Open your WSL terminal (`lesnar@DESKTOP...$)` and run:

```bash
# Go to the project directory (ensure you are in the right place)
cd ~/lesnar/LesnarAI

# Create a new Linux-native virtual environment
python3 -m venv .venv-wsl

# Activate it (NOTICE the source command, not Activate.ps1)
source .venv-wsl/bin/activate

# Install dependencies (ensure you have the system packages first if build fails)
pip install -r training/requirements.txt
```

## 2. Run PX4 SITL

We are cloning `PX4-Autopilot` to `../PX4-Autopilot` (relative to the project). Once finished:

```bash
# Go to PX4 directory
cd ../PX4-Autopilot

# Initial Setup (only if never done before on this machine)
# bash ./Tools/setup/ubuntu.sh 
# (You might need sudo password)

# Run the Simulation
# HEADLESS MODE (if no GUI server)
HEADLESS=1 make px4_sitl gz_x500

# OR WITH GUI (if you have XServer/WSLg)
make px4_sitl gz_x500
```

## 3. Run the Bridge

Open a **second** WSL terminal:

```bash
cd ~/lesnar/LesnarAI
source .venv-wsl/bin/activate

# Run the bridge
python training/px4_teacher_collect_gz.py --duration 120
```
