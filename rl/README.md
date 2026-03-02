# RL Depth-Avoid Scaffold (AirSim + PPO)

NOTE: This is a legacy AirSim-based RL scaffold. AirSim assets/env were moved under `legacy/`.

This folder gives you a minimal reinforcement learning setup that doesn't reinvent the stack:
- A Gymnasium environment wrapping AirSim depth images for navigation (`airsim_gym_env.py`).
- A PPO trainer using Stable-Baselines3 (`train_ppo.py`).

Prereqs:
- AirSim plugin loaded in Unreal and the map running in Play-In-Editor (PIE) with a multirotor.
- The legacy Python env at `legacy/airsim-env` already has `airsim`, `numpy`, `opencv-python`, and `torch`.

Install RL extras into the same venv (or a fresh one):

```powershell
# Using your existing venv
& .\legacy\airsim-env\Scripts\pip.exe install -r .\rl\requirements.txt
```

Run training:

```powershell
# Start Unreal and press Play first, then:
& .\legacy\airsim-env\Scripts\python.exe .\rl\train_ppo.py --timesteps 100000 --img_size 64 --hz 10 --max_speed 3 --max_yaw_rate 45
```

Notes:
- Observation is a 1x64x64 depth image normalized to [0,1].
- Action is [forward_factor, yaw_rate_factor] in [-1,1]. Forward is clamped to [0, max_speed] to discourage reversing.
- Reward encourages forward motion and keeping distance; penalizes close range and collisions.
- Tweak shaping and termination in `EnvConfig` for your scenario.

Exported model is saved under `runs/ppo_airsim/ppo_depth_avoid.zip`.
