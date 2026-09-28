#!/usr/bin/env bash
# WORKING SCRIPT - Uses PX4 default world (drone appears!)
# Run this: ./scripts/start_working.sh

set -e

cd ~/PX4-Autopilot
pkill -9 -f 'gz|px4|make' 2>/dev/null || true
sleep 2

echo "Starting PX4 SITL with WORKING drone spawn..."
echo "Drone will appear at coordinates (0, 0, 5) meters high"
echo ""

PX4_GZ_MODEL_POSE="0,0,5,0,0,0" make px4_sitl gz_x500
