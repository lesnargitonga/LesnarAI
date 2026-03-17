#!/usr/bin/env bash
set -euo pipefail

# EXACT README SOP (Terminal 1): Start the Physics Engine
cd "$HOME/PX4-Autopilot"
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$(pwd)/Tools/simulation/gz/models"
VERBOSITY="${LESNAR_GZ_VERBOSITY:-2}"
WORLD_SDF="${LESNAR_GZ_WORLD_SDF:-$HOME/workspace/LesnarAI/obstacles.sdf}"

# Headless mode reduces freezes on constrained GPUs/WSL GUI stacks.
if [[ "${LESNAR_GZ_HEADLESS:-0}" == "1" ]]; then
	gz sim "-v${VERBOSITY}" -r -s "$WORLD_SDF"
else
	gz sim "-v${VERBOSITY}" -r "$WORLD_SDF"
fi
