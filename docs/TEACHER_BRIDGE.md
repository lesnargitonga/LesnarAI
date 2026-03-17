# Teacher Bridge — Deep Reference

`training/px4_teacher_collect_gz.py`

---

## Table of Contents

1. [What It Is](#1-what-it-is)
2. [Architecture Overview](#2-architecture-overview)
3. [Component Reference](#3-component-reference)
   - 3.1 [Utility Helpers](#31-utility-helpers)
   - 3.2 [Map & Obstacle Layer](#32-map--obstacle-layer)
   - 3.3 [Pathfinding Layer (A\*)](#33-pathfinding-layer-a)
   - 3.4 [DroneState](#34-dronestate)
   - 3.5 [Physics Models](#35-physics-models)
   - 3.6 [Telemetry Listeners](#36-telemetry-listeners)
   - 3.7 [Redis Bridge](#37-redis-bridge)
4. [Operating Modes](#4-operating-modes)
5. [Main Flight Loop — Online Mode](#5-main-flight-loop--online-mode)
   - 5.1 [Navigation Stack](#51-navigation-stack)
   - 5.2 [Obstacle Avoidance System](#52-obstacle-avoidance-system)
   - 5.3 [Stability & Recovery Guards](#53-stability--recovery-guards)
   - 5.4 [Command Shaping & Output](#54-command-shaping--output)
   - 5.5 [Anti-Stall & Deadlock Escape](#55-anti-stall--deadlock-escape)
6. [Telemetry CSV Schema](#6-telemetry-csv-schema)
7. [Segmentation / Detection Log](#7-segmentation--detection-log)
8. [All CLI Arguments](#8-all-cli-arguments)
9. [Safe Presentation Profile](#9-safe-presentation-profile)
10. [Offline Mode](#10-offline-mode)
11. [Auto-Analysis](#11-auto-analysis)
12. [What We Have — Current State](#12-what-we-have--current-state)
13. [What We Can Integrate](#13-what-we-can-integrate)
14. [Known Gaps & Limitations](#14-known-gaps--limitations)

---

## 1. What It Is

`px4_teacher_collect_gz.py` is the core expert agent of the LesnarAI training pipeline. It serves two roles simultaneously:

**Role A — Live Operator Bridge**
Connects back-end → Redis → frontend to expose arm/disarm/takeoff/land/goto/mission commands from the web UI to the physical PX4 SITL instance. The app's fleet panel talks to this process at all times during simulation.

**Role B — Autonomous Teacher**
When not in pure bridge mode, the script pilots the drone fully autonomously: it plans A\* paths across the obstacle field, executes them with a multi-layer control stack, and records every control decision and sensor reading to CSV. This CSV is then used to train a student neural network via imitation learning.

The teacher can run in three modes:
- **Online** (default): full MAVSDK + Gazebo + Redis loop
- **Online Bridge Only** (`--bridge_only`): passive relay, waits for app commands
- **Offline** (`--offline`): pure Python simulation, no PX4 required

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                   px4_teacher_collect_gz.py                │
│                                                            │
│  ┌─────────┐   ┌──────────┐   ┌──────────────────────┐   │
│  │ Map/SDF │   │ GridMap  │   │  Physics Models       │   │
│  │ Obstacle│──▶│  A* Grid │   │  BatteryModel         │   │
│  │ Parser  │   │ +BFS clr │   │  WindModel (O-U)      │   │
│  └─────────┘   └──────────┘   └──────────────────────┘   │
│       │              │                                     │
│       ▼              ▼                                     │
│  ┌──────────────────────────────────────────────────────┐ │
│  │              MAIN FLIGHT LOOP  (async, 20 Hz)        │ │
│  │                                                      │ │
│  │  1. LIDAR simulation (72-ray, 360°)                  │ │
│  │  2. obstacle_avoidance_field (potential field)       │ │
│  │  3. A* replan (on demand / threat-triggered)         │ │
│  │  4. Pure-pursuit lookahead                           │ │
│  │  5. Avoidance blending                               │ │
│  │  6. Heading + speed control                          │ │
│  │  7. Body-frame guidance                              │ │
│  │  8. Stability/recovery guards                        │ │
│  │  9. Offboard VelocityNedYaw setpoint                 │ │
│  │ 10. CSV row write                                    │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────┐   ┌───────────────────────────────────┐ │
│  │ Redis Bridge │   │ MAVSDK Async Listeners            │ │
│  │ pub/sub cmds │   │ position · velocity · attitude    │ │
│  │ tel publish  │   │ IMU · battery · GPS quality       │ │
│  └──────────────┘   └───────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
                          │ CSV (58 cols, 20 Hz)
                          ▼
          dataset/px4_teacher/telemetry_god.csv
                          │
                          ▼
           train_student_px4.py → StudentNet.pt
```

---

## 3. Component Reference

### 3.1 Utility Helpers

| Function | Purpose |
|---|---|
| `log(msg)` | UTC-timestamped print + append to `teacher_runtime.log` |
| `acquire_single_instance_lock(token)` | `fcntl` exclusive lock under `/tmp/` — prevents two teacher processes for the same drone ID |
| `analyze_telemetry_csv(csv, report)` | End-of-run statistical analysis; writes JSON report with per-column stats, flight phase breakdown, obstacle-event rate |
| `wrap_deg(a)` | Wrap angle to [0, 360) |
| `shortest_diff(cur, tgt)` | Signed shortest angular distance in degrees |
| `clamp(v, lo, hi)` | Value clamp |
| `ned_to_map_xy(n, e)` | NED → map frame (X=East, Y=North) |
| `map_xy_to_ned(x, y)` | Map frame → NED |
| `heading_to_map_yaw(h)` | PX4 heading (°True, 0=North) → map-frame yaw (°, 0=East) |
| `map_yaw_to_heading(y)` | Inverse of above |
| `isa_temperature(alt_m)` | ISA standard atmosphere temperature at altitude |
| `isa_density(alt_m)` | ISA air density at altitude |

---

### 3.2 Map & Obstacle Layer

#### `class Obstacle`

Represents a single obstacle parsed from the SDF world file.

| Attribute | Description |
|---|---|
| `x, y` | World-frame centre position (m) |
| `radius` | Cylinder radius (m); 0 for boxes |
| `height` | Object height (m) |
| `is_box` | True for box geometry |
| `dx, dy` | Box full-extent dimensions (m) |

Key methods:
- `distance_to_point(px, py)` — exact surface clearance distance (exact for cylinder, SDF-aligned for box)
- `is_inside(px, py, margin)` — membership test used during grid rasterization
- `horizontal_size_m()` — returns the larger horizontal dimension; used as an obstacle-size weight in the threat calculation

#### `class Map`

Owns the full list of `Obstacle` objects and provides simulation services.

**`load_sdf(path)`**  
Parses Gazebo SDF XML — walks every `<model>/<link>/<collision>/<geometry>` node and instantiates either a cylinder or box `Obstacle`.

**`simulate_lidar(px, py, pz, yaw_deg, num_rays=72, max_dist=20.0)`**  
Full 360° ray-cast at 5° resolution. For each ray:
1. Filter nearby obstacles (within `max_dist` bounding sphere)
2. For each nearby obstacle compute ray-segment intersection (dot/cross product)
3. Return closest hit per ray (minimum over all obstacles)

Returns a `numpy` array of 72 floats (distances in metres).

**`obstacle_avoidance_field(px, py, rel_alt, heading_map_deg, route_ux, route_uy, lookahead_m=14.0, corridor_deg=65.0, safety_margin_m=2.0, vertical_clearance_m=1.2)`**  
Potential-field obstacle avoidance. Iterates all obstacles and for each one within the forward corridor:

1. Computes repulsion direction (away from obstacle centre)
2. Computes **tangential escape**: two perpendiculars to the repulsion vector; picks the one most aligned with the current route vector `(route_ux, route_uy)` so the drone slides around rather than slamming into the obstacle
3. Blends repulsion and tangential via `alpha = clearance / (safety_margin * 1.5)` clamped to [0, 0.6]
4. Weights the threat by:
   - `threat_dist`: how close the obstacle is relative to lookahead range
   - `heading_weight`: cosine of relative bearing (front-facing obstacles matter more)
   - `size_weight`: bigger obstacles get extra weight (clamped to [0.5, 2.0])
5. Accumulates `(repel_x, repel_y)` and tracks `min_clearance` and `max_threat`

Returns `(escape_x, escape_y, min_clearance, max_threat)`.

The `max_threat` field (`geom_threat` in CSV) is the primary scalar threat signal used for avoidance blending, proactive replan triggering, full-override decisions, and oscillation detection.

---

### 3.3 Pathfinding Layer (A\*)

#### `class GridMap`

Rasterizes all `Obstacle` objects onto a 2-D occupancy grid.

| Parameter | Default | Description |
|---|---|---|
| `resolution` | 1.0 m | Grid cell size |
| `margin` | 2.5 m | Safety margin inflated around every obstacle boundary |

**Construction steps:**
1. Compute bounding box of all obstacle centres + 20 m pad
2. Rasterize each obstacle: mark every grid cell whose world-coordinate centre is `is_inside(wx, wy, margin)` as blocked
3. **BFS clearance field**: starting from every blocked cell, propagate distance outward cell-by-cell using a BFS wavefront. Result is `self.clearance[gx, gy]` (grid-cell integer distances). The `clearance_at(gx, gy)` method returns this in metres.

The clearance field is precomputed once at startup and drives the clearance-weighted A\* step cost.

**Methods:**
- `world_to_grid(x, y)` / `grid_to_world(gx, gy)` — coordinate transforms
- `is_blocked(gx, gy)` — boundary-aware check
- `clearance_at(gx, gy)` — metres of clearance; 0 if blocked or out-of-bounds

#### `astar(grid_map, start, goal) → list[tuple]`

Standard A\* on the 8-connected grid with:
- **Euclidean heuristic** (`h = sqrt(Δgx² + Δgy²)`)
- **Clearance-weighted step cost**:
  ```
  clearance_penalty = CLEARANCE_PENALTY_MAX * max(0, 1 - nbr_clearance / CLEARANCE_PENALTY_RAMP)
  step_cost = step_dist + clearance_penalty
  ```
  - `CLEARANCE_PENALTY_MAX = 1.8 m` — maximum extra cost per step at a wall boundary
  - `CLEARANCE_PENALTY_RAMP = 4.0 m` — clearance at which penalty drops to zero

  This naturally routes A\* through open corridors and away from wall-hugging paths.
- **`nearest_free` snapping**: if start or goal is inside a blocked cell (can happen at startup or after a replan near an obstacle), BFS-searches up to radius 18 cells for the nearest free cell before planning.

#### `smooth_path(path, grid_map) → list[tuple]`

**String-pulling** via Bresenham line-of-sight.

Walks the raw A\* waypoint list with a sliding anchor:
- From each anchor, try to look ahead further and further
- As soon as the Bresenham line between anchor and lookahead passes through any blocked cell, insert the last clear waypoint as a bend and advance the anchor

Converts the staircase grid output of A\* into long, smooth straight segments — eliminating corner clips and reducing waypoint count significantly. Called at both main path-build sites (initial plan and proactive replan).

---

### 3.4 DroneState

`class DroneState` is a mutable shared object passed by reference to every async listener. It holds the most-recent MAVSDK telemetry values:

| Group | Fields |
|---|---|
| GPS position | `lat`, `lon`, `rel_alt` |
| NED position | `x`, `y`, `z` |
| NED velocity | `vx`, `vy`, `vz` |
| Attitude | `yaw`, `roll`, `pitch` |
| Status flags | `armed`, `in_air`, `mode` |
| Angular rates | `roll_rate_dps`, `pitch_rate_dps`, `yaw_rate_dps` |
| Body accel | `accel_x_ms2`, `accel_y_ms2`, `accel_z_ms2`, `imu_temp_deg_c` |
| Battery | `battery_voltage_v`, `battery_remaining_pct`, `battery_current_a` |
| GPS quality | `gps_fix_type`, `gps_num_sats`, `gps_hdop`, `altitude_msl_m` |

All fields start at safe neutral values (0.0 / False / `"UNKNOWN"`). Async listeners overwrite them as MAVSDK streams arrive.

---

### 3.5 Physics Models

#### `class BatteryModel`

Physics-based 4S LiPo battery model (DJI X500-class, 5 000 mAh / 74 Wh).

Power draw:
```
P = P_hover(108 W) + K_aero(0.55) × v_h² + m·g·v_climb / η_climb(0.72) + P_avionics(8 W)
```
Each `step(vx, vy, vz, dt)` call integrates amp-hours from state of charge, produces instantaneous current and power draw.

`flight_time_remaining(vx, vy, vz)` estimates remaining airborne time at current draw.

**Data policy**: battery model fields are written to CSV only when `--enable_battery_model` is explicitly passed. Real MAVSDK battery telemetry is always preferred; the model is additive.

#### `class WindModel`

Ornstein-Uhlenbeck correlated wind in NED frame.
- Mean-reversion rate: 0.04 s⁻¹  
- Volatility: 0.18 m/s/√s  
- Long-run mean: 0 (calm conditions on average)
- Realistic gusty range: 0–14 m/s  

`step(dt)` advances the stochastic process each tick. Wind fields (`wind_north_mps`, `wind_east_mps`, `wind_speed_mps`, `wind_dir_deg`) are always written to CSV unless `--disable_wind_model`. They are also published via Redis so the frontend can display live wind conditions.

---

### 3.6 Telemetry Listeners

Each listener is a standalone `asyncio.Task` that streams a MAVSDK subscription and writes into `DroneState`:

| Listener | MAVSDK subscription | Fields updated |
|---|---|---|
| `telemetry_listener` | `telemetry.position()` | lat, lon, rel_alt |
| `local_pos_listener` | `telemetry.position_velocity_ned()` | x, y, z, vx, vy, vz |
| `att_listener` | `telemetry.heading()` | yaw |
| `att_euler_listener` | `telemetry.attitude_euler()` | roll, pitch |
| `armed_listener` | `telemetry.armed()` | armed |
| `in_air_listener` | `telemetry.in_air()` | in_air |
| `flight_mode_listener` | `telemetry.flight_mode()` | mode |
| `battery_listener` | `telemetry.battery()` | voltage, remaining_pct |
| `imu_listener` | `telemetry.imu()` | angular rates, body accel, IMU temp |
| `gps_quality_listener` | `telemetry.gps_info()` | fix_type, num_sats |
| `raw_gps_listener` | `telemetry.raw_gps()` | hdop, altitude_msl_m |

All listeners silently absorb exceptions so a missing telemetry stream doesn't crash the main loop.

Additionally, `redis_telemetry_pump` runs as a separate task and re-publishes a condensed telemetry snapshot to the `telemetry` Redis channel every 250 ms for the frontend.

---

### 3.7 Redis Bridge

The teacher subscribes to the `commands` Redis channel and dispatches on `action`:

| Action | Behaviour |
|---|---|
| `arm` | `drone.action.arm()` with COMMAND_DENIED retry + re-apply PX4 params |
| `disarm` | Safety-checked (refuses if airborne); stops offboard first |
| `takeoff` | Arms, sets target altitude, calls PX4 AUTO.TAKEOFF, then re-engages offboard |
| `land` | Stops offboard, calls PX4 AUTO.LAND |
| `goto` | Converts lat/lon to local map coords, sets new A\* goal |
| `mission_start` | Parses waypoint list, triggers takeoff if needed, walks WPs sequentially via A\* |
| `mission_pause` | Sets `external_mission.status = "PAUSED"`, halts drone at current position |
| `mission_resume` | Restores active status, re-engages current WP |
| `mission_stop` | Clears external mission, reverts goal to current position |

The command drain loop processes **all queued messages** each tick before writing the CSV row, ensuring no command is skipped under burst conditions.

Telemetry published per tick includes: position, heading, speed, armed/in_air flags, mode, battery (if available), wind fields (if wind model enabled), and full mission status when a mission is active.

> **Drone-ID filtering**: commands with a non-empty `drone_id` field are silently dropped unless they match `args.drone_id`. This lets a single Redis server handle multi-drone setups.

---

## 4. Operating Modes

### Online Mode (default)
Full system: MAVSDK → PX4 SITL → Gazebo Harmonic. Requires `mavsdk`, `pyproj` not required (NED arithmetic only).

```bash
python3 training/px4_teacher_collect_gz.py \
  --system udpin://0.0.0.0:14540 \
  --hz 20 --alt 15 --duration 0
```

### Bridge-Only Mode (`--bridge_only`)
Teacher connects to PX4 but does not fly autonomously. Sits idle until the frontend dispatches a command via Redis. All telemetry listeners are active; CSV is written every tick. Used in production deployment where the human operator or the app controls the flight plan.

```bash
python3 training/px4_teacher_collect_gz.py --bridge_only --drone-id x500_0
```

### Offline Mode (`--offline`)
Pure Python simulation. No MAVSDK, no Gazebo. The drone position is Euler-integrated from velocity commands. LIDAR is simulated from the same `Map` geometry. Produces a minimal-schema CSV (16 columns). Useful for rapid pipeline testing and clearance-field/A\* algorithm development.

```bash
python3 training/px4_teacher_collect_gz.py --offline --duration 120
```

---

## 5. Main Flight Loop — Online Mode

The main loop (`collect_data()`) runs at `--hz` Hz (default 20 Hz) as a single `asyncio` coroutine. Each tick:

```
tick
 ├─ advance physics (wind model step, optional battery step)
 ├─ odometer accumulate
 ├─ anti-stall progress check (every progress_window_sec)
 ├─ check/run A* if path exhausted or empty
 ├─ pure-pursuit lookahead selection
 ├─ LIDAR simulation (72 rays)
 ├─ obstacle_avoidance_field
 ├─ proactive threat-triggered replan check
 ├─ front-distance robustness (EMA filter + glitch rejection)
 ├─ avoidance blend computation
 ├─ desired speed computation
 ├─ heading control + speed tapering
 ├─ attitude soft/hard guards
 ├─ recovery mode check
 ├─ 360° side-threat scan (during turns)
 ├─ oscillation detector
 ├─ body-frame guidance decomposition
 ├─ NED command via offboard.set_velocity_ned()
 ├─ CSV row write
 └─ Redis telemetry publish + command drain
```

### 5.1 Navigation Stack

**Goal selection** (`pick_new_goal()`):
- Samples 200 random free grid cells
- Selects the cell that maximises `dist + 0.35 × nearest_recent_goal_dist`
- Enforces minimum distance of 45 m from current position
- Maintains a `recent_goals` deque (last 5) to avoid revisiting areas
- Falls back to any free cell > 25 m away if no 45 m candidate found

**Path planning**:
1. Call `astar(grid, current, goal)` → raw grid waypoint list
2. Call `smooth_path(path, grid)` → string-pulled waypoints
3. Downsample: `path[::stride]` (stride = 2 in precision mode, 3 otherwise) + force-include final WP
4. Post-validate: check every WP clearance against all obstacles; if any WP grazes an obstacle within `--obstacle_safety_margin_m`, pick a new goal and replan

**Pure-pursuit lookahead**:
- Lookahead distance scales with current ground speed: `8.0 + 1.2×speed` (precision) or `6.0 + 0.8×speed` (normal), bounded to [8, 22] m or [6, 18] m
- Walks `current_path` from `path_index` forward until a WP is found beyond lookahead distance
- Trigger goal-reached when last WP is within 2 m

**Cross-track correction** (precision mode only):
- Computes signed cross-track error from the current path segment
- Adds `crosstrack_kp × cross_track_m` degrees correction to yaw target, capped at ±`crosstrack_heading_cap_deg`

---

### 5.2 Obstacle Avoidance System

Two-layer hybrid: **deliberative (A\*)** + **reactive (potential field)**.

#### Reactive Layer

`obstacle_avoidance_field()` produces a blended escape vector and `geom_threat` score each tick.

Avoidance blending:
```python
if geom_threat >= 0.90:
    avoid_blend = 1.0              # full override — ignore route
else:
    avoid_blend = clamp(avoidance_gain × geom_threat, 0.0, max_avoidance_blend)

nav_ux = (1 - avoid_blend) × route_ux + avoid_blend × avoid_ux
nav_uy = (1 - avoid_blend) × route_uy + avoid_blend × avoid_uy
```

Default gains: `avoidance_gain = 1.2`, `max_avoidance_blend = 0.85`.

#### Vector Cancellation Safety

When route and avoidance vectors are antiparallel (cancel to near-zero), the blended `nav_norm < 1e-6`. The fallback escapes along the **avoidance vector** rather than the route vector:
```python
if nav_norm < 1e-6:
    if avoid_norm > 1e-6:
        nav_ux, nav_uy = avoid_ux, avoid_uy   # escape AWAY from obstacle
    else:
        nav_ux, nav_uy = route_ux, route_uy   # last resort
```
This prevents the drone from being sent directly into the obstacle it's trying to avoid.

#### Front-Blocked Override

When `front_blocked_persisted` is active, the nav direction is **always overridden** to the avoidance escape vector (not just speed-reduced). Three-tier response:

| Condition | Action |
|---|---|
| Room + avoidance available | Override direction to `avoid_ux/uy`, crawl at `min_crawl_speed` |
| Tight corridor + avoidance | Override direction, slow to `min_crawl_speed × 0.5` |
| No avoidance vector | Full stop (`desired_speed = 0.0`) |

This eliminates the old bug where the drone would crawl forward *into* the wall it detected.

#### Stuck-Hover Timer

An independent speed-based stall detector runs **outside** the `front_blocked_persisted` branch, preventing oscillation between blocked/unblocked states from resetting the timer:

```python
if speed_now < 0.4 and near_obstacle:
    stuck_elapsed += dt
    if stuck_elapsed > 2.0:   # 2 s threshold
        pick_new_goal() → replan
else:
    stuck_elapsed = 0
```

Uses function-level state (`collect_data._stuck_hover_since`, `_stuck_hover_ticks`) so it accumulates continuously regardless of other subsystem states.

#### Deliberative Layer (A\* Replanning)

**Anti-stall replanning** — strike-based, every `progress_window_sec` (10 s):
- Strike counts if moved < `min_progress_m` (1.5 m) AND not in goal grace period AND not turning
- When `obstacle_braking` is active, strikes are **double-counted** (`+= 2` per window) to accelerate escape from stuck-near-obstacle situations
- After `replan_strikes` (5) consecutive strikes: pick new goal, replan
- Guarded by `replan_cooldown_sec` (3.5 s) between consecutive replans

**Proactive threat-triggered replan**:
- If `geom_threat ≥ 0.65` persists for ≥ 0.4 s → immediate A\* replan to current goal
- If A\* to current goal fails, picks a **new random goal** instead of silently failing
- Uses the same path → smooth → validate pipeline as the initial plan
- Resets `threat_trigger_since` after each replan

#### Front-Distance Robustness

Raw LIDAR front slice → glitch rejection → EMA smoothing:
- **Glitch rejection**: reject near-zero front readings when geometry clearance > 4 m and geometry threat < 0.2 (sensor artifact, not a real wall)
- **EMA smoothing**: `front_min_filtered = alpha × prev + (1−alpha) × raw` with `front_filter_alpha = 0.72`
- **Debounced hard-stop**: front block state only becomes active after `front_block_debounce_sec` (0.7 s) of continuous blockage; clears only after front clears by `front_recover_margin_m` (0.55 m) of hysteresis

Speed reduction from frontal obstacle:
```
obstacle_factor = (front_eval_dist − hard_stop_dist) / (slow_down_dist − hard_stop_dist)
```

Precision mode: `slow_down_dist = 5.5 m`, `hard_stop_dist = 1.6 m`  
Normal mode: `slow_down_dist = 8.0 m`, `hard_stop_dist = 2.8 m`

#### 360° Side-Threat Scan During Turns

When yaw error is large (`yaw_err_abs ≥ heading_align_slow_deg`), runs a 180°-corridor avoidance scan along the intended route direction. If the swept area has clearance < `slow_down_dist`, scales `desired_speed` by:
```
side_slow = (side_clearance − hard_stop_dist) / (slow_down_dist − hard_stop_dist)
```
This prevents the drone from flying into a wall it can see on the side while rotating.

#### Oscillation / Thrashing Detector

Maintains a rolling deque of the last 20 `(nav_ux, nav_uy)` direction vectors. Detects oscillation when:
```
dot(current_nav, avg_nav) < −0.5    # current direction opposes recent average
avg_len < 0.4                        # rolling average has low magnitude (alternating)
geom_threat > 0.3                    # genuinely near an obstacle
```

On detection:
1. Computes two perpendiculars to current heading vectors
2. Picks the perpendicular toward the most open LIDAR sector
3. Locks `nav_ux, nav_uy = escape_dir` for 1.5 s
4. Clears the history deque to prevent immediate re-trigger

---

### 5.3 Stability & Recovery Guards

**Attitude soft guard**:
- `soft_guard_deg = min(max_roll, max_pitch) × attitude_soft_guard_ratio` (default 55% of 30° = 16.5°)
- At `roll` or `pitch` above this: scale speed down proportionally toward `attitude_soft_min_speed_ratio = 0.18`

**Attitude hard guard + sideslip guard**:
- `max_roll_guard_deg = 30°`, `max_pitch_guard_deg = 30°`, `max_sideslip_guard_deg = 28°`
- Exceeded for `unstable_persist_sec = 0.35 s` → enter **recovery mode** for `recovery_hold_sec = 1.8 s`
- Recovery mode: cap speed at `recovery_speed_mps = 0.8 m/s`, cancel yaw commands (hold current heading), zero lateral commands

**Heading-stall detection**:
- If `|heading_error| ≥ 110°` AND `|progress_mps| ≤ 0.20 m/s` for `heading_stall_strikes = 12` consecutive ticks: force replan
- Grace period of 2.5 s after each new goal/replan before strikes can accumulate

---

### 5.4 Command Shaping & Output

**Speed hierarchy** (multiplicative):
```
desired_speed
  × heading_factor          (taper as yaw error grows)
  × attitude_factor         (taper under instability)
  × obstacle_factor         (frontal braking)
  × side_slow               (360° side threat during turns)
  × [crawl floor if blocked and corridor still open]
```

**Yaw rate limiting**: max `yaw_rate_limit = 65 °/s` per tick (clamped before applying).

**Body-frame decomposition**:
- Forward speed `fwd_des = desired_speed × cos(yaw_err_rad)` — never backward (clamped to ≥ 0)
- Lateral speed `lat_des = lat_gain × desired_speed × sin(yaw_err_rad)` — `lat_gain = 0.08` (precision) or `0.35` (normal)
- Heading alignment zones:
  - `yaw_err ≥ heading_align_stop_deg (38°)`: hard cap `fwd_des` at `heading_stop_forward_mps = 0.18 m/s`, zero lateral
  - `yaw_err ≥ heading_align_slow_deg (22°)`: scale by `heading_slow_forward_scale = 0.45` and `heading_slow_lateral_scale = 0.08`

**Tilt guard**:
```
tilt_target_deg = atan2(|lat_accel_cmd|, 9.81)
```
If tilt target exceeds `max_tilt_deg = 12°`, scale lateral commands back to hold tilt ≤ 12°.

**Acceleration limiting** + low-pass filter:
- World-frame: max 3.5 m/s² → clamp `Δv` each tick
- Body-frame: max 4.0 m/s² → clamp `fwd` and `lat` changes
- Light low-pass `α = 0.25` applied to world-frame command after accel clamping

**Output**: `drone.offboard.set_velocity_ned(VelocityNedYaw(vx, vy, vz, cmd_yaw))`

---

### 5.5 Anti-Stall & Deadlock Escape

Five overlapping systems prevent the drone from getting permanently stuck:

| System | Trigger | Response |
|---|---|---|
| Low-progress strikes | < 1.5 m in 10 s window × 5 strikes (2× near obstacles) | Pick new random goal, replan |
| Heading-stall strikes | Heading error > 110° + no progress × 12 ticks | Force replan |
| Oscillation escape | Nav direction reversal detected | 1.5 s lateral escape then replan |
| Proactive replan | `geom_threat ≥ 0.65` for 0.4 s | A\* replan to current goal (or new goal on failure) |
| Stuck-hover timer | Ground speed < 0.4 m/s near obstacle for 2 s | Pick new goal, replan |

All are cooldown-guarded (`replan_cooldown_sec = 3.5 s`) to prevent thrashing.

---

## 6. Telemetry CSV Schema

The output CSV has **58 columns** at up to 20 Hz.

### Original 24 Columns

| Column | Type | Description |
|---|---|---|
| `timestamp` | float | Unix epoch (s) |
| `lat` | float | Latitude (°) |
| `lon` | float | Longitude (°) |
| `rel_alt` | float | AGL altitude (m) |
| `vx` | float | NED north velocity (m/s) |
| `vy` | float | NED east velocity (m/s) |
| `vz` | float | NED down velocity (m/s) |
| `yaw` | float | Compass heading (°True, 0=N) |
| `cmd_vx` | float | Offboard north setpoint (m/s) |
| `cmd_vy` | float | Offboard east setpoint (m/s) |
| `cmd_vz` | float | Vertical setpoint (m/s) |
| `cmd_yaw` | float | Heading setpoint (°True) |
| `lidar_min` | float | Minimum of full 360° LIDAR scan (m) |
| `front_lidar_min` | float | Minimum of frontal sector LIDAR (m, debounced) |
| `cross_track_m` | float | Signed cross-track error from path segment (m) |
| `heading_error_deg` | float | Signed heading error to target yaw (°) |
| `sideslip_deg` | float | Estimated sideslip angle (°) |
| `progress_mps` | float | Speed component toward goal (m/s) |
| `geom_clearance_m` | float | Min clearance from potential-field scan (m) |
| `geom_threat` | float | Maximum threat score [0, ∞) from potential field |
| `tilt_target_deg` | float | Estimated required lateral tilt (°) |
| `lidar_json` | string | JSON array of 72 LIDAR beam distances |
| `goal_x` | float | Current goal X in map frame (m) |
| `goal_y` | float | Current goal Y in map frame (m) |

### Enriched 34 Columns

| Column | Type | Description |
|---|---|---|
| `roll_deg` | float | Roll angle (°) |
| `pitch_deg` | float | Pitch angle (°) |
| `roll_rate_dps` | float | Roll rate (°/s) |
| `pitch_rate_dps` | float | Pitch rate (°/s) |
| `yaw_rate_dps` | float | Yaw rate (°/s) |
| `accel_fwd_ms2` | float | Body-frame forward acceleration (m/s²) |
| `accel_right_ms2` | float | Body-frame right acceleration (m/s²) |
| `accel_down_ms2` | float | Body-frame down acceleration (m/s²) |
| `battery_voltage_v` | float/empty | Battery voltage from MAVSDK (V) |
| `battery_current_a` | float/empty | Battery current from model or MAVSDK (A) |
| `battery_remaining_pct` | float/empty | Remaining capacity (%) |
| `power_draw_w` | float/empty | Estimated power draw from model (W) |
| `energy_consumed_wh` | float/empty | Cumulative energy consumed by model (Wh) |
| `flight_time_remaining_s` | float/empty | Model estimated flight time remaining (s) |
| `wind_north_mps` | float/empty | Synthetic wind north component (m/s) |
| `wind_east_mps` | float/empty | Synthetic wind east component (m/s) |
| `wind_speed_mps` | float/empty | Synthetic wind speed magnitude (m/s) |
| `wind_dir_deg` | float/empty | Meteorological wind-from direction (°) |
| `temperature_deg_c` | float | ISA temperature at altitude (°C) |
| `air_density_kg_m3` | float | ISA air density at altitude (kg/m³) |
| `ground_speed_mps` | float | Horizontal ground speed magnitude (m/s) |
| `course_over_ground_deg` | float | Course over ground (°, 0=East) |
| `distance_to_goal_m` | float | Euclidean distance to current goal (m) |
| `path_wps_remaining` | int | Remaining waypoints in active A\* path |
| `mission_elapsed_s` | float | Seconds since first airborne |
| `total_distance_flown_m` | float | Cumulative odometry (m) |
| `flight_phase` | int | 0=ground 1=takeoff 2=cruise 3=approach 4=hover 5=land |
| `gps_fix_type` | int | GPS fix type (0=none, 3=3D, 6=RTK) |
| `gps_num_sats` | int | Number of visible satellites |
| `gps_hdop` | float | Horizontal dilution of precision |
| `altitude_msl_m` | float | MSL altitude from raw GPS (m) |
| `obstacle_count_near` | int | Count of LIDAR beams < `slow_down_dist` |
| `effective_airspeed_mps` | float | Ground speed minus estimated wind contribution (m/s) |
| `is_replanning` | int | 1 if A\* replan was issued this tick |
| `is_recovering` | int | 1 if stability recovery mode is active |

Battery and energy model columns are empty strings when the battery model is disabled. Wind columns are empty when the wind model is disabled.

---

## 7. Segmentation / Detection Log

Each run also writes a `logs/seg_diag_<YYYYMMDD_HHMMSS>.csv` with columns:

```
drone_id, detected_class, confidence, timestamp
```

Populated while the drone is airborne, whenever:
- `geom_threat > 0.15` OR `front_conf > 0.3`
- Class is `obstacle` (threat > 0.35 or conf > 0.55) or `proximity_alert`

This feed also surfaces in the dashboard **Analytics** panel.

---

## 8. All CLI Arguments

### Core

| Flag | Default | Description |
|---|---|---|
| `--drone-id` | `SENTINEL-01` | Drone identifier (also used for instance lock and Redis filtering) |
| `--out` | `dataset/px4_teacher/telemetry_god.csv` | Output CSV path (created on startup) |
| `--system` | `udpin://0.0.0.0:14540` | MAVLink system address |
| `--duration` | `0` | Run time in seconds (0 = unlimited) |
| `--bridge_only` | false | Passive relay mode: no autonomous navigation |
| `--no_lock` | false | Disable single-instance lock (debug) |
| `--sdf_path` | `obstacles.sdf` | World file for obstacle map; also reads `$SDF_PATH` env |
| `--offline` | false | Pure Python mode without PX4 |
| `--mavsdk-server` | `auto` | MAVSDK server host (`auto` = let mavsdk-python spawn it) |
| `--mavsdk-port` | `50051` | MAVSDK server port |
| `--redis-host` | `127.0.0.1` | Redis host |
| `--redis-port` | `6379` | Redis port |
| `--auto_analyze` | true | Analyze telemetry CSV on exit |
| `--analysis_report` | auto | Explicit JSON report output path |

### Flight Profile

| Flag | Default | Description |
|---|---|---|
| `--hz` | `20.0` | Main loop rate (Hz) |
| `--alt` | `15.0` | Target cruise altitude AGL (m) |
| `--base_speed` | `2.2` | Base navigation speed (m/s) |
| `--max_speed` | `4.2` | Maximum navigation speed (m/s) |
| `--min_crawl_speed` | `0.6` | Minimum forward crawl near hard-stop threshold (m/s) |
| `--yaw_rate_limit` | `65.0` | Maximum yaw rate command (°/s) |
| `--precision_mode` | true | Enable Falcon precision path-tracking controller |
| `--safe_presentation_profile` | true | Conservative safety limits for demos |

### Obstacle Avoidance

| Flag | Default | Description |
|---|---|---|
| `--obstacle_lookahead_m` | `14.0` | Potential-field lookahead range (m) |
| `--obstacle_corridor_deg` | `65.0` | Forward corridor half-angle for avoidance (°) |
| `--obstacle_safety_margin_m` | `2.0` | Extra safety margin around obstacles (m) |
| `--obstacle_height_clearance_m` | `1.2` | Ignore obstacles lower than alt − this (m) |
| `--obstacle_sector_deg` | `14.0` | Front LIDAR sector half-width (°) |
| `--avoidance_gain` | `1.2` | Scales `geom_threat` → avoidance blend ratio |
| `--max_avoidance_blend` | `0.85` | Upper cap on avoidance blend (ignored at threat ≥ 0.9) |

### Heading / Precision Controller

| Flag | Default | Description |
|---|---|---|
| `--crosstrack_kp` | `3.0` | Cross-track to heading correction gain (°/m) |
| `--crosstrack_heading_cap_deg` | `14.0` | Max cross-track correction (°) |
| `--max_lateral_ratio` | `0.04` | Max lateral / max_speed in precision mode |
| `--forward_hold_deg` | `45.0` | Reduce forward speed when heading error > this |
| `--heading_align_slow_deg` | `22.0` | Begin heavy speed taper (°) |
| `--heading_align_stop_deg` | `38.0` | Near-stop translation zone (°) |
| `--heading_slow_min_ratio` | `0.22` | Minimum speed ratio in slow zone |
| `--heading_stop_speed_ratio` | `0.10` | Maximum speed ratio in stop zone |
| `--heading_stop_forward_mps` | `0.18` | Max forward speed in stop zone (m/s) |
| `--heading_slow_forward_scale` | `0.45` | Forward multiplier in slow zone |
| `--heading_slow_lateral_scale` | `0.08` | Lateral multiplier in slow zone |

### Lateral / Tilt Control

| Flag | Default | Description |
|---|---|---|
| `--max_lateral_accel_mps2` | `2.0` | Max lateral acceleration command (m/s²) |
| `--max_tilt_deg` | `12.0` | Max target tilt angle (°) |

### Stability & Recovery

| Flag | Default | Description |
|---|---|---|
| `--max_roll_guard_deg` | `30.0` | Hard roll guard limit (°) |
| `--max_pitch_guard_deg` | `30.0` | Hard pitch guard limit (°) |
| `--attitude_soft_guard_ratio` | `0.55` | Soft guard threshold as fraction of hard limit |
| `--attitude_soft_min_speed_ratio` | `0.18` | Minimum speed ratio under soft attitude damping |
| `--max_sideslip_guard_deg` | `28.0` | Sideslip guard limit (°) |
| `--sideslip_speed_guard_mps` | `1.2` | Minimum speed before sideslip guard activates |
| `--unstable_persist_sec` | `0.35` | Instability persistence before recovery mode (s) |
| `--recovery_hold_sec` | `1.8` | Recovery mode hold duration (s) |
| `--recovery_speed_mps` | `0.8` | Max speed during recovery (m/s) |

### LIDAR Filtering

| Flag | Default | Description |
|---|---|---|
| `--front_filter_alpha` | `0.72` | EMA smoothing factor for front clearance |
| `--front_block_debounce_sec` | `0.7` | Debounce before hard-stop engages (s) |
| `--front_recover_margin_m` | `0.55` | Hysteresis above hard-stop to clear blocked state |
| `--front_zero_glitch_threshold_m` | `0.05` | Treat front < this as potential glitch (m) |
| `--front_zero_ignore_geom_clear_m` | `4.0` | Ignore glitch if geometry clearance > this (m) |
| `--front_zero_ignore_geom_threat` | `0.2` | Ignore glitch if geometry threat < this |

### Anti-Stall / Replan

| Flag | Default | Description |
|---|---|---|
| `--progress_window_sec` | `10.0` | Seconds between progress checks |
| `--min_progress_m` | `1.5` | Movement threshold for a passing check (m) |
| `--replan_strikes` | `5` | Consecutive failing checks before replan |
| `--goal_grace_sec` | `9.0` | Grace period after new goal (s) |
| `--replan_heading_hold_deg` | `80.0` | Suppress progress strikes while turning (°) |
| `--replan_cooldown_sec` | `3.5` | Minimum time between forced replans (s) |
| `--heading_stall_err_deg` | `110.0` | Heading error threshold for stall detection (°) |
| `--heading_stall_progress_mps` | `0.20` | Progress threshold for stall counting (m/s) |
| `--heading_stall_strikes` | `12` | Consecutive stall ticks before forced replan |
| `--heading_stall_grace_sec` | `2.5` | Grace period after each replan (s) |
| `--metrics_log_sec` | `1.5` | Seconds between FALCON quality log lines |

### Student / Domain Randomization / Dynamic Obstacles

| Flag | Default | Description |
|---|---|---|
| `--student_model` | `""` | Path to trained student `.pt` checkpoint for closed-loop inference |
| `--student_blend` | `0.0` | Teacher/student command blend ratio (0.0=teacher only, 1.0=student only) |
| `--domain_randomization` | false | Enable `SensorNoiseModel` noise injection for sim2real transfer |
| `--dynamic_obstacles` | false | Enable LIDAR-driven dynamic grid updates via `detect_dynamic_obstacles()` |

### Physics Models

| Flag | Default | Description |
|---|---|---|
| `--disable_wind_model` | false | Disable Ornstein-Uhlenbeck wind (wind on by default) |
| `--enable_battery_model` | false | Add CSV-only battery model columns |
| `--enable_synthetic_models` | false | Legacy alias: enable both wind and battery models |

---

## 9. Safe Presentation Profile

When `--safe_presentation_profile` is active (default), the following parameters are **clamped to lower values** before the main loop starts:

| Parameter | Cap |
|---|---|
| `hz` | 15 Hz |
| `base_speed` | 0.9 m/s |
| `max_speed` | 1.8 m/s |
| `min_crawl_speed` | 0.22 m/s |
| `yaw_rate_limit` | 24 °/s |
| `avoidance_gain` | 0.55 |
| `max_avoidance_blend` | 0.32 |
| `max_lateral_accel_mps2` | 0.55 m/s² |
| `max_tilt_deg` | 5.5° |
| `recovery_speed_mps` | 0.35 m/s |

This mode is designed for live frontend demos where a visually smooth, conservative flight is preferred over maximum data-collection coverage.

---

## 10. Offline Mode

`collect_data_offline()` is a synchronous (non-async) fallback. Key differences:

- Position is Euler-integrated: `px += cmd_vx × dt`, `py += cmd_vy × dt`
- Yaw is integrated from a simple proportional yaw-rate command
- No battery, wind, or enriched telemetry
- CSV has 16 columns (original subset only)
- `smooth_path()` is NOT called (raw A\* output is used with `stride=2`)
- No Redis bridge
- `auto_analyze` still works

Useful for validating the A\* + clearance-field pipeline without a full PX4 stack.

---

## 11. Auto-Analysis

At end of run (normal exit or `finally`), if `--auto_analyze` is active:

`analyze_telemetry_csv(csv_path, report_path)` reads the entire CSV and produces a JSON report including:
- Row count, flight duration, distance flown
- Per-column descriptive statistics (mean, std, min, max)
- Phase distribution (% time in each flight phase)
- Obstacle event rate (% ticks with `geom_threat > 0.15`)
- LIDAR frontal blockage event count

The report is written to `<csv_stem>_analysis.json` unless `--analysis_report` is set explicitly.

---

## 12. What We Have — Current State

### Data Pipeline
- Full sensor fusion: MAVSDK position/velocity/attitude/IMU/battery/GPS → 58-col CSV at 20 Hz
- Synthetic physics augmentation: Ornstein-Uhlenbeck wind model, ISA atmosphere, 4S LiPo battery model
- 72-beam 360° simulated LIDAR from SDF geometry (usable for downstream sensor simulation)

### Navigation
- Static A\* over BFS-clearance-weighted occupancy grid (1 m resolution, 2.5 m obstacle inflation)
- String-pulled path smoothing (Bresenham LOS)
- Pure-pursuit lookahead (speed-adaptive, [8, 22] m precision / [6, 18] m normal)
- Cross-track correction (precision mode)

### Avoidance
- Potential-field reactive avoidance with tangential escape
- Two-layer blend (reactive + deliberative)
- Proactive threat-triggered replan at `geom_threat ≥ 0.65` (0.4 s persistence)
- Full override at `geom_threat ≥ 0.90`
- Vector cancellation safety: falls back to avoidance escape (not route) when vectors cancel
- Front-blocked override: always steers away from obstacle, never crawls into it
- Independent stuck-hover timer (speed < 0.4 m/s near obstacle for 2 s → replan)
- Obstacle-braking double-count: progress strikes accumulate 2× faster near obstacles
- Path clearance validation post-plan
- 360° side-threat scan during turns
- Oscillation/thrashing detector with lateral escape
- A\* replan fallback: picks new goal when replan to current goal fails

### Safety
- Roll/pitch hard + soft guards
- Sideslip guard
- Recovery mode with speed cap + hold-heading
- Front-distance EMA filter + glitch rejection + debounced hard-stop
- Anti-stall strike system + heading-stall detector

### Bridge
- Full Redis command/telemetry protocol (arm/disarm/takeoff/land/goto/mission)
- Multi-drone filtering by drone ID
- External mission state machine (ACTIVE/PAUSED/FAILED/COMPLETED)
- Offboard mode management + PX4 param tuning

### Student Model (train_student_px4.py)
- `Px4TeacherDataset`: accepts `list[Path]` with glob expansion, loads from multiple CSVs
- Enriched 93-dim feature vector: `[72 LIDAR, sin(yaw), cos(yaw), 19 scalar keys]` → targets `[cmd_vx, cmd_vy, cmd_vz, cmd_yaw]`
- `StudentNet`: enriched `93→128→128→64→4` with Dropout(0.1); legacy `75→64→64→4`
- Threat-weighted sampling: `weight = 1 + 4 × min(threat, 1)` — 5× oversampling of critical avoidance rows
- AdamW optimizer with weight decay, CosineAnnealingLR, gradient clipping at 1.0
- Train/val split with best-model checkpointing by validation loss
- Checkpoint saves `{state_dict, in_dim, out_dim, enriched, best_val_loss, scalar_keys}`

### Closed-Loop Student Inference (NEW)
- `StudentController` class loads trained `.pt` checkpoint, reconstructs `StudentNet`
- Per-tick inference: LIDAR + state → `(cmd_vx, cmd_vy, cmd_vz, cmd_yaw)`
- Configurable teacher/student command blending via `--student_blend` (0.0=teacher, 1.0=student)
- Supports both enriched and legacy feature vectors

### Domain Randomization (NEW)
- `SensorNoiseModel` class injects realistic sensor noise for sim2real transfer
- LIDAR: σ=0.08m Gaussian + 0.5% ray dropout
- IMU accel: ±0.03 bias + σ=0.15 white noise; gyro: ±0.5°/s bias + σ=1.5°/s
- GPS: σ=0.8m position; heading: σ=1.5°; thrust: 0.92–1.0 global factor
- Enabled via `--domain_randomization` CLI flag

### Dynamic Obstacle Detection (NEW)
- `GridMap.detect_dynamic_obstacles()`: compares actual vs expected LIDAR per ray
- Where actual < expected − 2m, ray-casts hit to world coords and marks cells blocked
- `GridMap.mark_dynamic_obstacle()`: incremental BFS clearance update (not full rebuild)
- Enabled via `--dynamic_obstacles` CLI flag

### Evaluation Harness (NEW)
- `training/evaluate_student.py`: replays CSV LIDAR traces through student model
- Metrics: MAE (overall, per-channel), direction agreement, speed MAE, collision proxy rate
- Regime-specific accuracy: avoidance MAE (high-threat) vs cruise MAE (low-threat)
- Automated deployment grade (A–F) based on accuracy + collision proxy thresholds

---

## 13. What We Can Integrate

### A. Richer Feature Input for the Student ✅ IMPLEMENTED

The student now uses 93 enriched features (72 LIDAR + 2 sin/cos yaw + 19 scalar keys from the 58-col CSV). Includes `geom_threat`, `geom_clearance_m`, `roll/pitch/yaw rates`, `cross_track_m`, `heading_error_deg`, `wind`, `distance_to_goal_m`, and more. Architecture upgraded to `93→128→128→64→4` with dropout.

### B. Closed-Loop Inference ✅ IMPLEMENTED

`StudentController` class loads a trained `.pt` checkpoint and runs per-tick inference. Commands are blended with teacher output via `--student_blend` (0.0=teacher, 1.0=student). Creates a progressive DAgger-ready handover loop: collect → train → blend → collect richer data with student → retrain.

### C. Multi-Run Dataset Combiner ✅ IMPLEMENTED

`Px4TeacherDataset` now accepts `list[Path]` with glob expansion. CLI `--data` takes `nargs="+"` supporting patterns like `runs/*/telemetry_*.csv`. Enables overnight batch collection + single combined training run.

### D. Dynamic/Real-Time Obstacle Integration ✅ IMPLEMENTED

- **LIDAR-driven grid update**: `GridMap.detect_dynamic_obstacles()` compares actual vs expected LIDAR; where actual < expected − 2m, ray-casts hit to world coords and marks cells blocked
- **Incremental GridMap update**: `GridMap.mark_dynamic_obstacle()` runs BFS only from newly blocked cells, not full rebuild
- Enabled via `--dynamic_obstacles` CLI flag
- **Remaining**: Gazebo topic bridge for moving model poses (not yet implemented)

### E. Scenario Randomisation + Curriculum

Currently goals are random free cells ≥ 45 m away. Could add:
- **Obstacle density curriculum**: start training runs in sparse regions, gradually route goals through tight corridors
- **Speed curriculum**: begin with `--base_speed 1.0` and ramp after N successful runs
- **Wind curriculum**: `--disable_wind_model` early, then enable with increasing `WindModel.SIGMA`
- The `pick_new_goal()` function already has a scoring framework — scoring weights can be CLI arguments

### F. Imitation Learning Improvements

Current student: pure behavioural cloning (MSE on teacher actions). Options:
- **DAgger (Dataset Aggregation)**: run student in blended mode, collect disagreement cases, add to training set, retrain
- **Action weighting**: weight loss higher for sharp avoidance manoeuvres (high `geom_threat` rows) vs. boring cruise rows — the current dataset is heavily imbalanced
- **Recurrent / temporal context**: add a GRU layer to let the student learn temporal patterns (oscillation, turn completion, acceleration ramps)
- **Phase-conditional heads**: separate output heads per `flight_phase` (cruise vs. approach vs. recovery) — each specialises on a different regime

### G. Evaluation Harness ✅ IMPLEMENTED

`training/evaluate_student.py` replays CSV LIDAR traces through the student model and reports:
- MAE (overall + per-channel), MSE, direction agreement, speed MAE
- Collision proxy rate: fraction where student exceeds teacher speed by >0.5 m/s near high-threat obstacles
- Regime-specific: avoidance MAE (threat>0.5) vs cruise MAE (threat<0.1)
- Automated deployment grade (A–F)
- Optional JSON report output via `--report`

### H. Map Visualiser

GridMap and A\* output are never visualised. Could export:
- Occupancy grid + clearance field as PNG
- A\* path + smoothed path as GeoJSON overlay for the frontend map component (the frontend already renders obstacles via GeoJSON at `drone_simulation/data/obstacles.geojson`)

### I. Segmentation Model Integration

`seg_diag_*.csv` logs obstacle detections derived from the LIDAR potential-field. This is synthetic. The `models/deeplabv3_cityscapes/` and `models/unet_synth/` directories contain trained visual segmentation models. Bridging to the teacher:
- Subscribe to Gazebo camera topic → run inference → compare visual obstacles with LIDAR/SDF obstacles
- Cross-validate: if visual detector fires where SDF has no obstacle → potential map update trigger

---

## 14. Known Gaps & Limitations

| Gap | Impact | Status |
|---|---|---|
| ~~Static obstacle map (SDF-only)~~ | ~~Can't avoid obstacles not in SDF file~~ | ✅ Fixed: LIDAR-based dynamic grid update (§13.D) |
| ~~Student not connected to bridge~~ | ~~Trained model has no effect on actual flights~~ | ✅ Fixed: `StudentController` + `--student_blend` (§13.B) |
| ~~Single-file dataset~~ | ~~Multi-run batches require shell globbing workaround~~ | ✅ Fixed: Multi-path `Px4TeacherDataset` (§13.C) |
| ~~No class imbalance handling~~ | ~~Student over-trains on cruise, under-trains on avoidance~~ | ✅ Fixed: Threat-weighted sampling (5× for critical rows) |
| ~~No evaluation harness~~ | ~~Can't measure student quality without live flight~~ | ✅ Fixed: `evaluate_student.py` (§13.G) |
| ~~A\* grid rebuilt from scratch on replan~~ | ~~O(W×H) BFS each replan can stall loop~~ | ✅ Fixed: Incremental clearance updates via `mark_dynamic_obstacle()` |
| ~~Offline mode lacks path smoothing~~ | ~~Offline CSVs have staircase paths~~ | ✅ Fixed: `smooth_path()` added to `collect_data_offline()` |
| ~~Obstacle freeze: drone stuck in front of wall forever~~ | ~~4 cascading bugs: strikes suppressed by `obstacle_braking`, vector cancellation sent drone into obstacle, front-blocked crawled forward into wall, stuck-hover timer never accumulated~~ | ✅ Fixed: obstacle-braking accelerates strikes, vector cancellation escapes away, front-blocked overrides direction, independent stuck-hover timer (§5.2) |
| AI Lab Redis commands not handled by teacher | Frontend AI Lab sends `enable_student`, `enable_noise`, `update_avoidance` etc. but teacher ignores them | ⚠️ Open: teacher Redis listener only handles arm/disarm/takeoff/land/goto/mission commands |
| No `/eval/run` orchestrator endpoint | Evaluation tab calls `POST /eval/run` which doesn't exist yet | ⚠️ Open: needs handler in `scripts/runtime_orchestrator.py` |
| ~~`_wps_rem` always 0 in online mode~~ | ~~`path_wps_remaining` column always zero~~ | ✅ Fixed: Wired to `len(current_path) - path_index` |
| ~~Freeze/hover deadlock~~ | ~~Drone freezes near obstacles when front_blocked_persisted + geom critical~~ | ✅ Fixed: Lateral escape crawl + stuck-hover timer with forced replan |
| No domain randomization feedback | Noise added but not compared to real sensor noise | Add real hardware noise profiling |
| No 3-D obstacle handling | All avoidance is 2-D (relies on `vertical_clearance_m` heuristic) | Extend ray-cast to elevation bands |
| Wind model not fedback to PX4 | Synthetic wind is in CSV only; PX4 doesn't know about it | Inject via MAVSDK wind estimation plugin or QGC wind injection |
| No recurrent student architecture | Student has no temporal context (single-frame policy) | Add GRU/LSTM layer for oscillation/turn learning |
| Gazebo dynamic model tracking | Moving obstacles in Gazebo not yet tracked | Subscribe to `~/world/default/dynamic_pose/info` |
