#!/bin/bash
set -e

echo "=== Lesnar AI WSL Setup ==="

# 1. Python Environment
if [ ! -d ".venv-wsl" ]; then
    echo "[*] Creating Python virtual environment (.venv-wsl)..."
    python3 -m venv .venv-wsl
else
    echo "[*] Virtual environment (.venv-wsl) already exists."
fi

echo "[*] Activating .venv-wsl..."
source .venv-wsl/bin/activate

echo "[*] Installing dependencies..."
pip install --upgrade pip
pip install -r training/requirements.txt
pip install mavsdk redis numpy opencv-python pandas

# 2. PX4 Check
# Check Home directory first (faster IO in WSL)
if [ -d "$HOME/PX4-Autopilot" ]; then
    PX4_DIR="$HOME/PX4-Autopilot"
    echo "[+] Found existing PX4-Autopilot at $PX4_DIR"
elif [ -d "../PX4-Autopilot" ]; then
    PX4_DIR="../PX4-Autopilot"
    echo "[+] Found existing PX4-Autopilot at $PX4_DIR"
else
    echo "[!] PX4-Autopilot NOT found."
    echo "    Cloning to $HOME/PX4-Autopilot (WSL native is faster)..."
    git clone https://github.com/PX4/PX4-Autopilot.git "$HOME/PX4-Autopilot" --recursive
    PX4_DIR="$HOME/PX4-Autopilot"
fi

echo "=== Setup Complete ==="
echo "To activate environment: source .venv-wsl/bin/activate"
echo "To run PX4 SITL:"
echo "    cd $PX4_DIR"
echo "    make px4_sitl gz_x500"
