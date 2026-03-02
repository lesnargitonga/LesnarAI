import gymnasium as gym
import numpy as np
import time
import argparse
from pathlib import Path
try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    def tqdm(x, **kwargs):
        return x
import airsim
import math

# Minimal VFH logic copied to ensure stability
def compute_angles(w: int, hfov_deg: float) -> np.ndarray:
    cols = np.arange(w, dtype=np.float32)
    return (cols / max(1, w - 1) - 0.5) * float(hfov_deg)

def angular_clearance(depth_m: np.ndarray, hfov_deg: float) -> tuple[np.ndarray, np.ndarray]:
    h, w = depth_m.shape
    # Focus on the center band (avoid seeing the floor/ceiling too much)
    # UPDATED: 30-70% (Avoid seeing own propellers during banking turns)
    r0, r1 = int(0.30 * h), int(0.70 * h)
    roi = depth_m[r0:r1, :]
    
    # 10th percentile distance (conservative clearance)
    cl = np.percentile(roi, 10, axis=0) if roi.size > 0 else np.zeros(w)
    
    # Smooth
    k = 5
    if w >= k:
        kernel = np.ones(k) / k
        cl = np.convolve(cl, kernel, mode='same')
        
    angles = compute_angles(w, hfov_deg)
    return angles, cl

# Re-implementing a more robust Teacher class
class VFHExpert:
    def __init__(self, cfg):
        self.last_steer = 0.0
        self.last_speed_cmd = 0.0 # Initialize speed memory
        self.cfg = cfg
        self._prev_dist_to_target_m = None
        self._no_progress_steps = 0
        self._recovery_steps_left = 0
        self._recovery_yaw_sign = 1.0
        self._last_chosen_steer = 0.0
        # Avoidance lock: when we need to avoid, commit to one side for a short window.
        # This removes "scan" behavior (left/right dithering) that wastes time.
        self._avoid_lock_steps = 0
        self._avoid_lock_sign = 1.0

        

    def predict(self, obs, info):
        # Unpack observation
        depth_norm = obs['visual']
        if isinstance(depth_norm, np.ndarray) and depth_norm.ndim == 3:
            depth_norm = depth_norm[0]
        kinematics = obs['kinematics']
        
        # Kinematics map:
        # 10: sin(heading_error), 11: cos(heading_error)
        sin_h = float(kinematics[10])
        cos_h = float(kinematics[11])
        heading_error = math.atan2(sin_h, cos_h)
        target_yaw = heading_error
        
        # Distance (prefer info as it's exact)
        target_dist = float(kinematics[9]) * 50.0
        if isinstance(info, dict) and "dist_to_target" in info:
            target_dist = float(info["dist_to_target"])
        
        # Recover depth in meters
        depth_m = depth_norm * float(self.cfg.max_depth_clip_m)
        
        # VFH Analysis
        angles, clearance = angular_clearance(depth_m, 90.0)
        
        # Map goal to VFH histogram index
        goal_deg = float(np.degrees(target_yaw))
        goal_clamp = float(np.clip(goal_deg, -44.0, 44.0)) # Keep slightly inside index bounds
        
        # Find index for goal direction
        idx_goal = int(np.argmin(np.abs(angles - goal_clamp)))
        # Check clearance along the goal path (average 3 degrees around goal)
        idx_min = max(0, idx_goal - 2)
        idx_max = min(len(clearance), idx_goal + 3)
        goal_path_clearance = np.min(clearance[idx_min:idx_max]) if idx_max > idx_min else 0.0

        # Front clearance (center) for emergency braking logic
        idx_front = int(np.argmin(np.abs(angles - 0.0)))
        front_clear_m = float(clearance[idx_front])

        # --- Decision Logic ---
        
        SAFE_GOAL_HORIZON = 6.0
        # If the path to the goal is clear, go there directly.
        # Logic: If clearance > 6m, or if clearance > target_dist (goal is closer than obstacle), it's safe.
        is_goal_safe = (goal_path_clearance > SAFE_GOAL_HORIZON) or (goal_path_clearance > (target_dist + 0.5))



        # Check for Lock Expiration
        if self._avoid_lock_steps > 0:
            self._avoid_lock_steps -= 1
            # Smart Lock: If we see the goal is definitely safe now, unlock early.
            # (Fixes "weird behavior" where it keeps turning after passing the obstacle)
            if is_goal_safe and abs(goal_deg) < 20.0:
                 self._avoid_lock_steps = 0

        if is_goal_safe and self._avoid_lock_steps <= 0:
            # Mode: DIRECT GOAL SEEK
            chosen_steer = goal_deg
            
        else:
            # Mode: AVOIDANCE / VFH
            
            mask_side = np.ones_like(angles, dtype=bool)
            
            # If locked, force searching only on that side (smoothly)
            if self._avoid_lock_steps > 0:
                if self._avoid_lock_sign > 0: # Right
                    mask_side = angles > -5.0 # Allow slight overlap to center
                else: # Left
                    mask_side = angles < 5.0

            SAFE_MIN = 4.0
            
            # Filter clearance by side lock
            valid_indices = np.where(mask_side)[0]
            if len(valid_indices) == 0: valid_indices = np.arange(len(angles)) # Fallback
            
            sub_clearance = clearance[valid_indices]
            sub_angles = angles[valid_indices]
            
            # Identify safe valleys
            safe_mask = sub_clearance > SAFE_MIN
            
            if np.any(safe_mask):
                # Pick safe angle closest to goal
                safe_angles = sub_angles[safe_mask]
                scores = np.abs(safe_angles - goal_deg)
                best_idx_local = np.argmin(scores)
                chosen_steer = float(safe_angles[best_idx_local])
                
                # Trigger Lock if we are deviating significantly from goal
                if abs(chosen_steer - goal_deg) > 15.0 and self._avoid_lock_steps <= 0:
                    self._avoid_lock_steps = 25 # Commit for ~1s+
                    self._avoid_lock_sign = 1.0 if chosen_steer > 0 else -1.0

            else:
                # No safe path > 4m? Panic / Max Clearance
                best_idx_local = np.argmax(sub_clearance)
                chosen_steer = float(sub_angles[best_idx_local])
                
                # Definitely lock this choice
                if self._avoid_lock_steps <= 0:
                    self._avoid_lock_steps = 15
                    self._avoid_lock_sign = 1.0 if chosen_steer > 0 else -1.0

        # --- Speed Control ---
        
        # Standard distance schedule
        if target_dist > 5.0: dist_scale = 1.0
        elif target_dist > 3.0: dist_scale = 0.90
        elif target_dist > 1.5: dist_scale = 0.65
        else: dist_scale = 0.35
        
        base_speed = float(self.cfg.max_speed_mps) * dist_scale
        
        # Obstacle braking (Emergency)
        # UPDATED: Replaced "Stepped" braking (2.0m -> 0.2 speed) with "Linear" braking.
        # This prevents the "stop-start" behavior when hovering around 2.0m clearance.
        
        idx_chosen = int(np.argmin(np.abs(angles - np.clip(chosen_steer, -44, 44))))
        chosen_clearance = float(clearance[idx_chosen])
        
        # Scale speed linearly based on clearance:
        # Full speed at 2.2m+, down to 0.1 at 0.5m.
        # User Feedback: "visible braking" -> 4.0m was too conservative.
        BRAKE_DIST_MAX = 2.2
        BRAKE_DIST_MIN = 0.5
        
        brake_factor = np.clip((chosen_clearance - BRAKE_DIST_MIN) / (BRAKE_DIST_MAX - BRAKE_DIST_MIN), 0.1, 1.0)
        
        # Override braking if we are purposefully flying to a safe goal
        if is_goal_safe:
             brake_factor = 1.0
        
        # REMOVED: turn_factor (User wants seamless turning, not turn-in-place)
        base_speed = base_speed * brake_factor
        
        # Absolute safety stop (very close)
        # UPDATED: User wants "no stopping at all".
        # If very close, CRAWL but do not stop.
        if chosen_clearance < 0.6:
            base_speed = 0.2
            
        # Also check purely frontal collision if we are moving fast
        # UPDATED: Only brake for front wall if we are actually trying to fly straight!
        # If we are turning hard (scanning past a wall), don't brake.
        # Reduced threshold from 20 to 5 degrees. If we are turning AT ALL, trust the turn.
        if abs(chosen_steer) < 5.0 and front_clear_m < 1.0 and base_speed > 0.5:
             base_speed *= 0.5
             
        # Stuck detection (recovery)
        progress_eps_m = 0.03
        if self._prev_dist_to_target_m is None or not np.isfinite(self._prev_dist_to_target_m):
            self._prev_dist_to_target_m = target_dist

        if target_dist > 1.0:
            if target_dist > (self._prev_dist_to_target_m - progress_eps_m):
                self._no_progress_steps += 1
            else:
                self._no_progress_steps = 0
        else:
            self._no_progress_steps = 0
        self._prev_dist_to_target_m = target_dist

        # Stuck -> Recovery
        if self._recovery_steps_left <= 0 and self._no_progress_steps >= 60:
             self._recovery_steps_left = 25 # ~1-2s backup
             self._recovery_yaw_sign = -1.0 if chosen_steer > 0 else 1.0 # Try reversing logic
             self._no_progress_steps = 0

        # Output Generation
        self._last_chosen_steer = float(chosen_steer)
        
        # Smooth steer
        EMA = 0.30 
        self.last_steer = EMA * chosen_steer + (1-EMA) * self.last_steer
        
        # Velocity Smoothing (EMA)
        # Fixes "stops severally" by preventing rapid drops in command.
        SPEED_EMA = 0.20 # Slower reaction to speed drops, smoother flight
        target_physical_speed = EMA * base_speed + (1-EMA) * self.last_speed_cmd
        self.last_speed_cmd = target_physical_speed
        
        denom = float(self.cfg.max_speed_mps) if float(self.cfg.max_speed_mps) > 1e-6 else 1.0
        norm_vx = target_physical_speed / denom
        norm_vy = 0.0
        norm_vz = 0.0
        
        # Yaw Rate
        steer_deadband_deg = 3.0
        steer_for_rate = 0.0 if abs(float(self.last_steer)) < steer_deadband_deg else float(self.last_steer)
        # Using the reverted gain parameter
        k_p = 1.8
        yaw_rate_deg = float(np.clip(k_p * steer_for_rate, -0.85 * float(self.cfg.max_yaw_rate_dps), 0.85 * float(self.cfg.max_yaw_rate_dps)))
        norm_yaw_rate = yaw_rate_deg / self.cfg.max_yaw_rate_dps
        
        # Forward commitment (prevent sitting)
        if self._recovery_steps_left <= 0 and target_dist > 3.0 and chosen_clearance > 3.5 and front_clear_m > 2.5:
             norm_vx = max(float(norm_vx), 0.35)
             
        # Recovery override
        if self._recovery_steps_left > 0:
            self._recovery_steps_left -= 1
            norm_vx = -0.15 # Slight reverse
            norm_yaw_rate = float(np.clip(0.65 * self._recovery_yaw_sign, -1.0, 1.0))

        actions = np.array([norm_vx, norm_vy, norm_vz, norm_yaw_rate], dtype=np.float32)
        return np.clip(actions, -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=5000, help='Total expert steps to collect')
    parser.add_argument('--out', type=str, default='expert_data.npz')
    parser.add_argument('--no-compress', action='store_true', help='Save with np.savez (no compression) to reduce memory/CPU for huge runs')
    args = parser.parse_args()
    
    from airsim_gym_env import AirSimDroneEnv, EnvConfig
    
    # Init Env
    cfg = EnvConfig(
        img_size=64,
        enable_domain_randomization=False,  # Expert needs reliable physics
        # Prefer smooth translation but keep yaw responsive (avoid sluggish turning).
        action_smoothing_beta=0.40,
        action_smoothing_beta_yaw=0.25,
        # Faster than crawl, but stable/smooth.
        max_speed_mps=2.6,
        max_yaw_rate_dps=110.0,
        # Reduce depth RPC load during long collections.
        vision_skip_frames=8,
        # Teacher mode: keep the control path simple.
        # (We rely on VFH steering + Guardian braking; avoid stacking extra controllers.)
        min_altitude_m=2.0,
        # Lower safe distance so the Guardian doesn't start scaling vx down while obstacles are still far.
        guardian_safe_dist_m=1.6,
        # Minimal altitude hold prevents slow sink while the teacher is turning/braking.
        enable_altitude_hold=True,
        altitude_hold_kp=0.7,
        altitude_hold_deadband_m=0.15,
        altitude_hold_max_correction_mps=0.8,
        enable_tilt_protection=False,
        enable_ground_cushion=False,
        enable_command_rate_limit=False,
        # Continuous mission: chain targets without returning home.
        continuous_mission=True,
        land_on_goal=True,
        # Smoother landing (USER REQUEST: "landing is so violent" -> "make the landing faster its so slow")
        goal_touchdown_speed_mps=0.6, # Compromise: Fast but controlled
        goal_touchdown_hold_sec=0.5,

        # Avoid spawning targets inside obstacle geometry
        avoid_targets_in_obstacles=True,
        target_obstacle_clearance_m=2.5,
        obstacle_actor_regex="LESNAR_GEN_.*",
        obstacles_file="unreal_tools/ue_obstacles.blocks.json",
        # Curriculum: start near (~5m) and grow as targets are completed.
        success_dist_m=0.75,
        target_spawn_min_m=5.0,
        target_spawn_max_m=12.0, # Harder start
        target_spawn_growth_per_success_m=2.0,
        target_spawn_max_total_m=120.0,
        # Give the expert room to fly without being terminated by the leash.
        geofence_radius_m=250.0,
        geofence_buffer_m=60.0,
        # Effectively disable episode time limits during long collections.
        max_steps=1000000000,

        # Avoid repeatedly spawning "target behind obstacle" tasks in long unattended runs.
        # ENABLED (User Request: "increase obstacles")
        obstacle_curriculum_prob=0.3,
    )
    env = AirSimDroneEnv(config=cfg)
    
    expert = VFHExpert(cfg)
    
    # Storage (preallocate: avoids massive Python list overhead on long runs)
    n = int(args.steps)
    img = int(cfg.img_size)
    log_visual = np.empty((n, img, img), dtype=np.float16)
    log_kin = np.empty((n, 19), dtype=np.float32)
    log_actions = np.empty((n, 4), dtype=np.float32)
    log_rewards = np.empty((n,), dtype=np.float32)
    log_dist_to_target = np.empty((n,), dtype=np.float32)
    log_depth_p10_m = np.empty((n,), dtype=np.float32)
    log_depth_mean_m = np.empty((n,), dtype=np.float32)
    log_term_reason = np.empty((n,), dtype=object)
    
    obs, info = env.reset()

    # Anti-repeat guard: if we keep failing the same target the same way,
    # don't keep reusing it forever (that creates duplicated trajectories).
    last_fail_key = None
    last_fail_count = 0
    
    print(f"Collecting {args.steps} steps from VFH Expert...")
    
    for i in tqdm(range(n)):
        # 1. Expert prediction
        action = expert.predict(obs, info)
        
        # USER REQUEST: "if the drone scans for a while that process becomes terminated"
        # Check explicit stuck timeout from expert state
        if expert._no_progress_steps > 300: # ~15s
            # Force reset
            if i > 0:
                log_term_reason[i-1] = "stuck_timeout"
            
            print(f"[COLLECT] Stuck timeout (steps={expert._no_progress_steps}). Triggering landing/reset.")
            obs, info = env.reset()
            # Reset expert memory
            expert.last_steer = 0.0
            expert._prev_dist_to_target_m = None
            expert._no_progress_steps = 0
            expert._recovery_steps_left = 0
            
            # For this step 'i', we record the FRESH reset state.
            # The previous step 'i-1' is now terminal.
            # Action is irrelevant for a reset step usually, but we need to fill the array.
            action = np.zeros(4, dtype=np.float32)

        # 2. Store (save without channel dim; BC dataset will add it back)
        vis = obs['visual']
        if isinstance(vis, np.ndarray) and vis.ndim == 3:
            vis = vis[0]
        log_visual[i] = vis.astype(np.float16, copy=False)
        log_kin[i] = obs['kinematics'].astype(np.float32, copy=False)
        log_actions[i] = action.astype(np.float32, copy=False)
        
        # 3. Simulate
        obs, reward, terminated, truncated, info = env.step(action)
        log_rewards[i] = float(reward)

        if isinstance(info, dict):
            log_dist_to_target[i] = float(info.get("dist_to_target", np.nan))
            log_depth_p10_m[i] = float(info.get("depth_p10_m", np.nan))
            log_depth_mean_m[i] = float(info.get("depth_mean_m", np.nan))
            log_term_reason[i] = str(info.get("termination_reason", "none"))
        else:
            log_dist_to_target[i] = np.nan
            log_depth_p10_m[i] = np.nan
            log_depth_mean_m[i] = np.nan
            log_term_reason[i] = "none"
        
        if terminated or truncated:
            reason = info.get("termination_reason", "unknown") if isinstance(info, dict) else "unknown"
            tgt_xy = tuple(np.round(np.array(env.target_position[:2], dtype=np.float32), 1).tolist())
            fail_key = (str(reason), tgt_xy)
            if fail_key == last_fail_key:
                last_fail_count += 1
            else:
                last_fail_key = fail_key
                last_fail_count = 1

            # Helpful console breadcrumb when watching the sim.
            if isinstance(info, dict):
                dt = info.get("dist_to_target", None)
                print(f"[COLLECT] episode_end reason={reason} repeat={last_fail_count} dist_to_target={dt}")
            else:
                print(f"[COLLECT] episode_end reason={reason} repeat={last_fail_count}")

            # Keep the SAME target on time_limit/geofence *briefly* (for mission continuity),
            # but if we repeat the same failure too many times, force a new target.
            if reason in {"time_limit", "geofence"} and last_fail_count <= 2:
                tgt = np.array(env.target_position, dtype=np.float32)
                obs, info = env.reset(options={"target_position": tgt})
            else:
                obs, info = env.reset()

            # Reset internal expert memory for the next episode chunk
            expert.last_steer = 0.0
            expert._prev_dist_to_target_m = None
            expert._no_progress_steps = 0
            expert._recovery_steps_left = 0
            
    # Save
    print(f"Saving to {args.out}...")
    saver = np.savez if bool(args.no_compress) else np.savez_compressed
    saver(
        args.out,
        visual=log_visual,
        kinematics=log_kin,
        actions=log_actions,
        rewards=log_rewards,
        dist_to_target=log_dist_to_target,
        depth_p10_m=log_depth_p10_m,
        depth_mean_m=log_depth_mean_m,
        termination_reason=log_term_reason,
    )
    print("Done! Median Reward:", float(np.nanmedian(log_rewards)))
    env.close()

if __name__ == "__main__":
    main()
