#!/usr/bin/env bash
set -euo pipefail

# EXACT README SOP (Terminal 2): Start the Autopilot Brain
killall -9 px4 2>/dev/null || true
cd "$HOME/PX4-Autopilot"
export PX4_GZ_STANDALONE=1
export PX4_GZ_WORLD=obstacles
export GZ_IP="${GZ_IP:-127.0.0.1}"  # must match the world's transport (start_gz_world.sh)
make px4_sitl gz_x500
