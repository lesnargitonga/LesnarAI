import asyncio
import argparse
import atexit
import csv
import fcntl
import json
import math
import os
import random
import time
import heapq
from collections import deque
from statistics import mean
import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

try:
    import redis.asyncio as redis
    import redis as sync_redis
except ImportError:
    redis = None
    sync_redis = None

try:
    # Only needed for online / PX4 mode
    from mavsdk import System
    from mavsdk.offboard import OffboardError, VelocityNedYaw
except Exception:
    System = None
    OffboardError = Exception
    VelocityNedYaw = None

LOG_PATH = "teacher_runtime.log"
_LOCK_BASENAME = "lesnar_px4_teacher_collect_gz"
_LOCK_HANDLE = None

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

log("Teacher script started")


def _sanitize_lock_token(token: str) -> str:
    token = (token or "").strip() or "global"
    token = token[:64]
    safe = []
    for ch in token:
        if ch.isalnum() or ch in ("_", "-"):
            safe.append(ch)
        else:
            safe.append("_")
    return "".join(safe) or "global"


def acquire_single_instance_lock(lock_token: str) -> None:
    global _LOCK_HANDLE
    safe = _sanitize_lock_token(lock_token)
    lock_path = f"/tmp/{_LOCK_BASENAME}.{safe}.lock"
    _LOCK_HANDLE = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(
            f"Another px4_teacher_collect_gz.py instance is already running for lock_token={safe!r}"
        ) from exc
    _LOCK_HANDLE.write(str(os.getpid()))
    _LOCK_HANDLE.flush()

    def _cleanup_lock():
        global _LOCK_HANDLE
        try:
            if _LOCK_HANDLE is not None:
                fcntl.flock(_LOCK_HANDLE, fcntl.LOCK_UN)
                _LOCK_HANDLE.close()
        except Exception:
            pass
        _LOCK_HANDLE = None

    atexit.register(_cleanup_lock)


def analyze_telemetry_csv(csv_path: str, report_path: str | None = None) -> dict:
    rows = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception as exc:
        log(f"Auto-analysis failed to read telemetry CSV: {exc}")
        return {}

    if len(rows) < 5:
        log("Auto-analysis skipped: not enough telemetry rows.")
        return {}

    def getf(row: dict, key: str, default: float = 0.0) -> float:
        try:
            return float(row.get(key, default))
        except Exception:
            return default

    ts = [getf(r, "timestamp", 0.0) for r in rows]
    duration_s = max(0.0, ts[-1] - ts[0]) if len(ts) > 1 else 0.0
    sample_rate_hz = (len(rows) / duration_s) if duration_s > 1e-6 else 0.0

    speeds = []
    cmd_speeds = []
    progresses = []
    front_clears = []
    xtracks = []
    heading_err_abs = []

    for row in rows:
        vx = getf(row, "vx")
        vy = getf(row, "vy")
        vz = getf(row, "vz")
        cvx = getf(row, "cmd_vx")
        cvy = getf(row, "cmd_vy")
        speeds.append(math.sqrt(vx * vx + vy * vy + vz * vz))
        cmd_speeds.append(math.sqrt(cvx * cvx + cvy * cvy))
        progresses.append(getf(row, "progress_mps"))
        front_clears.append(getf(row, "front_lidar_min", getf(row, "lidar_min", 20.0)))
        xtracks.append(abs(getf(row, "cross_track_m")))
        heading_err_abs.append(abs(getf(row, "heading_error_deg")))

    low_speed_pct = 100.0 * sum(1 for s in speeds if s < 0.2) / len(speeds)
    low_progress_pct = 100.0 * sum(1 for p in progresses if p < 0.15) / len(progresses)
    front_zero_pct = 100.0 * sum(1 for d in front_clears if d <= 0.05) / len(front_clears)
    cmd_zero_pct = 100.0 * sum(1 for s in cmd_speeds if s <= 0.05) / len(cmd_speeds)

    segments = []
    start = None
    for index, value in enumerate(speeds):
        if value < 0.2 and start is None:
            start = index
        if value >= 0.2 and start is not None:
            segments.append((start, index - 1))
            start = None
    if start is not None:
        segments.append((start, len(speeds) - 1))

    long_low_speed_segments = []
    for start, end in segments:
        if end > start and (ts[end] - ts[start]) >= 2.0:
            long_low_speed_segments.append(
                {
                    "t_start_s": round(ts[start] - ts[0], 2),
                    "t_end_s": round(ts[end] - ts[0], 2),
                    "duration_s": round(ts[end] - ts[start], 2),
                }
            )

    abrupt_stops = []
    for i in range(1, len(speeds)):
        dt = ts[i] - ts[i - 1]
        if dt <= 1.0 and (speeds[i - 1] - speeds[i]) > 2.0:
            abrupt_stops.append(
                {
                    "t_s": round(ts[i] - ts[0], 2),
                    "speed_before": round(speeds[i - 1], 3),
                    "speed_after": round(speeds[i], 3),
                    "front_lidar_min": round(front_clears[i], 3),
                    "progress_mps": round(progresses[i], 3),
                }
            )

    diagnosis = []
    if front_zero_pct > 30.0 and low_speed_pct > 60.0 and cmd_zero_pct > 60.0:
        diagnosis.append(
            "Protective hold likely dominated the run: front clearance stayed near zero and commanded velocity stayed near zero."
        )
    if mean(heading_err_abs) > 25.0:
        diagnosis.append(
            "High average heading error: consider reducing yaw aggression or increasing turn grace before low-progress penalties."
        )
    if mean(xtracks) > 3.0:
        diagnosis.append(
            "Cross-track error is high: route-tracking gains or lookahead distance need refinement."
        )
    if not diagnosis:
        diagnosis.append("No dominant failure signature detected; run appears nominal or mixed.")

    report = {
        "file": str(csv_path),
        "rows": len(rows),
        "duration_s": round(duration_s, 3),
        "sample_rate_hz": round(sample_rate_hz, 3),
        "metrics": {
            "speed_avg_mps": round(mean(speeds), 3),
            "speed_max_mps": round(max(speeds), 3),
            "progress_avg_mps": round(mean(progresses), 3),
            "progress_min_mps": round(min(progresses), 3),
            "front_clear_avg_m": round(mean(front_clears), 3),
            "front_clear_min_m": round(min(front_clears), 3),
            "xtrack_avg_m": round(mean(xtracks), 3),
            "xtrack_max_m": round(max(xtracks), 3),
            "heading_err_avg_deg": round(mean(heading_err_abs), 3),
            "heading_err_max_deg": round(max(heading_err_abs), 3),
            "low_speed_pct": round(low_speed_pct, 2),
            "low_progress_pct": round(low_progress_pct, 2),
            "front_zero_pct": round(front_zero_pct, 2),
            "cmd_zero_pct": round(cmd_zero_pct, 2),
        },
        "events": {
            "long_low_speed_segments": long_low_speed_segments,
            "abrupt_stops": abrupt_stops,
        },
        "diagnosis": diagnosis,
    }

    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            log(f"Auto-analysis report written: {report_path}")
        except Exception as exc:
            log(f"Auto-analysis report write failed: {exc}")

    log(
        "Auto-analysis summary | "
        f"duration={report['duration_s']:.1f}s rows={report['rows']} "
        f"speed_avg={report['metrics']['speed_avg_mps']:.2f}mps "
        f"progress_avg={report['metrics']['progress_avg_mps']:.2f}mps "
        f"low_speed={report['metrics']['low_speed_pct']:.1f}% "
        f"front_zero={report['metrics']['front_zero_pct']:.1f}%"
    )
    for item in diagnosis:
        log(f"Auto-analysis diagnosis: {item}")

    return report

"""
GOD-MODE TEACHER COLLECTOR
--------------------------
1. Parses obstacles.sdf to load the EXACT world map.
2. Uses this 'ground truth' to simulate a PERFECT LiDAR scan.
3. Why? Because the real Gazebo Lidar has been unreliable (stuck at 20m).
4. Saves this clean, noise-free simulated Lidar data for the student to learn from.
"""

# --- UTILS ---
def wrap_deg(a: float) -> float:
    return (a + 180) % 360 - 180

def shortest_diff(current: float, target: float) -> float:
    return wrap_deg(target - current)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def ned_to_map_xy(north: float, east: float) -> tuple[float, float]:
    # PX4 local position is NED (north, east). SDF/world map is ENU-like (x=east, y=north).
    return east, north


def map_xy_to_ned(map_x: float, map_y: float) -> tuple[float, float]:
    # Convert map frame x/y back to NED north/east command channels.
    return map_y, map_x


def heading_to_map_yaw(heading_deg: float) -> float:
    # PX4 heading: 0=north, 90=east (clockwise from north)
    # map/math yaw: 0=+x(east), 90=+y(north) (counter-clockwise from +x)
    return wrap_deg(90.0 - heading_deg)


def map_yaw_to_heading(yaw_deg: float) -> float:
    return wrap_deg(90.0 - yaw_deg)

class Obstacle:
    def __init__(self, x, y, radius, height, is_box=False, dx=0, dy=0):
        self.x = x
        self.y = y
        self.radius = radius  # For cylinder
        self.height = height
        self.is_box = is_box
        self.dx = dx  # For box
        self.dy = dy  # For box

    def distance_to_point(self, px, py):
        if not self.is_box:
            dist = math.sqrt((px - self.x) ** 2 + (py - self.y) ** 2) - self.radius
            return max(0.0, dist)
        else:
            tx = abs(px - self.x)
            ty = abs(py - self.y)
            dx = max(tx - (self.dx / 2), 0)
            dy = max(ty - (self.dy / 2), 0)
            return math.sqrt(dx * dx + dy * dy)

    def is_inside(self, px, py, margin=0.0):
        if not self.is_box:
            dist_sq = (px - self.x) ** 2 + (py - self.y) ** 2
            return dist_sq < (self.radius + margin) ** 2
        else:
            half_x = (self.dx / 2) + margin
            half_y = (self.dy / 2) + margin
            return (abs(px - self.x) < half_x) and (abs(py - self.y) < half_y)

    def horizontal_size_m(self):
        if self.is_box:
            return max(self.dx, self.dy)
        return self.radius * 2.0


class Map:
    def __init__(self, sdf_path):
        self.obstacles = []
        self.load_sdf(sdf_path)

    def load_sdf(self, path):
        print(f"Loading map from {path}...")
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            world = root.find("world")
            for model in world.findall("model"):
                pose_elem = model.find("pose")
                if pose_elem is None:
                    continue
                parts = [float(f) for f in pose_elem.text.split()]
                mx, my, mz = parts[0], parts[1], parts[2]

                link = model.find("link")
                if link is None:
                    continue
                collision = link.find("collision")
                if collision is None:
                    continue
                geometry = collision.find("geometry")
                if geometry is None:
                    continue

                if geometry.find("box") is not None:
                    size_str = geometry.find("box").find("size").text
                    dims = [float(f) for f in size_str.split()]
                    self.obstacles.append(Obstacle(mx, my, 0, dims[2], True, dims[0], dims[1]))
                elif geometry.find("cylinder") is not None:
                    cyl = geometry.find("cylinder")
                    r = float(cyl.find("radius").text)
                    h = float(cyl.find("length").text)
                    self.obstacles.append(Obstacle(mx, my, r, h, False))

            print(f"Loaded {len(self.obstacles)} obstacles.")
        except Exception as e:
            print(f"Failed to load map: {e}")

    def simulate_lidar(self, px, py, pz, yaw_deg, num_rays=72, max_dist=20.0):
        ranges = np.ones(num_rays) * max_dist
        fov = 360.0
        angle_step = fov / num_rays

        nearby = []
        for obs in self.obstacles:
            dist_center = math.sqrt((px - obs.x) ** 2 + (py - obs.y) ** 2)
            max_dim = max(obs.dx, obs.dy) if obs.is_box else obs.radius * 2
            if dist_center - (max_dim / 2) < max_dist:
                nearby.append(obs)

        yaw_rad = math.radians(yaw_deg)

        for i in range(num_rays):
            rel_angle = -180 + (i * angle_step)
            ray_angle = math.radians(rel_angle) + yaw_rad
            rx = math.cos(ray_angle)
            ry = math.sin(ray_angle)

            min_hit = max_dist

            for obs in nearby:
                ox = obs.x - px
                oy = obs.y - py

                dot = ox * rx + oy * ry
                if dot > 0:
                    cross = abs(ox * ry - oy * rx)
                    size = (max(obs.dx, obs.dy) / 2) if obs.is_box else obs.radius
                    if cross < size:
                        dist = dot - size
                        if dist < min_hit:
                            min_hit = dist

            ranges[i] = max(0.0, min_hit)

        return ranges

    def obstacle_avoidance_field(
        self,
        px,
        py,
        rel_alt,
        heading_map_deg,
        route_ux=0.0,
        route_uy=0.0,
        lookahead_m=14.0,
        corridor_deg=65.0,
        safety_margin_m=2.0,
        vertical_clearance_m=1.2,
    ):
        """Return (escape_x, escape_y, min_clearance, max_threat).

        The escape vector blends pure repulsion with a tangential component that
        slides the drone around the obstacle rather than slamming into it.  The
        tangent direction is chosen to be the one that most closely aligns with
        the current route, so the drone takes the shortest detour.
        """
        repel_x = 0.0
        repel_y = 0.0
        min_clearance = lookahead_m
        max_threat = 0.0

        for obs in self.obstacles:
            # Ignore obstacles that are well below current flight altitude.
            if rel_alt > (obs.height + vertical_clearance_m):
                continue

            clearance = max(0.0, obs.distance_to_point(px, py) - safety_margin_m)
            if clearance > lookahead_m:
                continue

            vec_to_obs_x = obs.x - px
            vec_to_obs_y = obs.y - py
            center_dist = math.hypot(vec_to_obs_x, vec_to_obs_y)
            if center_dist < 1e-6:
                continue

            bearing_to_obs = math.degrees(math.atan2(vec_to_obs_y, vec_to_obs_x))
            rel_bearing = shortest_diff(heading_map_deg, bearing_to_obs)
            if abs(rel_bearing) > corridor_deg:
                continue

            dir_away_x = -vec_to_obs_x / center_dist
            dir_away_y = -vec_to_obs_y / center_dist

            # Tangential escape: two perpendiculars to the repulsion vector.
            # Pick the one that best aligns with the current route so the drone
            # slides smoothly around the obstacle toward the goal.
            tan1_x, tan1_y = -dir_away_y, dir_away_x
            tan2_x, tan2_y = dir_away_y, -dir_away_x
            t1_align = tan1_x * route_ux + tan1_y * route_uy
            t2_align = tan2_x * route_ux + tan2_y * route_uy
            if t1_align >= t2_align:
                tan_x, tan_y = tan1_x, tan1_y
            else:
                tan_x, tan_y = tan2_x, tan2_y

            # alpha scales from 0 (pure repulsion when inside safety margin)
            # to 0.6 (strong tangential component when there is clearance room).
            alpha = clamp(clearance / max(1e-6, safety_margin_m * 1.5), 0.0, 0.60)
            esc_x = (1.0 - alpha) * dir_away_x + alpha * tan_x
            esc_y = (1.0 - alpha) * dir_away_y + alpha * tan_y
            esc_norm = math.hypot(esc_x, esc_y)
            if esc_norm > 1e-6:
                esc_x /= esc_norm
                esc_y /= esc_norm
            else:
                esc_x, esc_y = dir_away_x, dir_away_y

            threat_dist = clamp((lookahead_m - clearance) / max(1e-6, lookahead_m), 0.0, 1.0)
            heading_weight = clamp(math.cos(math.radians(rel_bearing)), 0.0, 1.0)
            size_weight = clamp(obs.horizontal_size_m() / 4.0, 0.5, 2.0)
            threat = threat_dist * heading_weight * size_weight

            repel_x += threat * esc_x
            repel_y += threat * esc_y
            min_clearance = min(min_clearance, clearance)
            max_threat = max(max_threat, threat)

        return repel_x, repel_y, min_clearance, max_threat


# --- PATHFINDING ---
class GridMap:
    def __init__(self, obstacles, resolution=1.0, margin=1.5):
        self.res = resolution
        pad = 20
        all_x = [o.x for o in obstacles] + [0]
        all_y = [o.y for o in obstacles] + [0]
        self.min_x = min(all_x) - pad
        self.max_x = max(all_x) + pad
        self.min_y = min(all_y) - pad
        self.max_y = max(all_y) + pad

        self.width = int((self.max_x - self.min_x) / self.res)
        self.height = int((self.max_y - self.min_y) / self.res)

        print(
            f"Grid Size: {self.width}x{self.height}, Bounds: x[{self.min_x:.1f},{self.max_x:.1f}] y[{self.min_y:.1f},{self.max_y:.1f}]"
        )

        self.grid = np.zeros((self.width, self.height), dtype=bool)

        print("Rasterizing obstacles...")
        for o in obstacles:
            size = (max(o.dx, o.dy) if o.is_box else o.radius * 2) + (margin * 2)
            steps = int(size / self.res) + 2

            cx, cy = self.world_to_grid(o.x, o.y)

            for i in range(-steps, steps + 1):
                for j in range(-steps, steps + 1):
                    gx, gy = cx + i, cy + j
                    if 0 <= gx < self.width and 0 <= gy < self.height:
                        wx, wy = self.grid_to_world(gx, gy)
                        if o.is_inside(wx, wy, margin):
                            self.grid[gx, gy] = True

    def world_to_grid(self, x, y):
        gx = int((x - self.min_x) / self.res)
        gy = int((y - self.min_y) / self.res)
        return gx, gy

    def grid_to_world(self, gx, gy):
        wx = (gx * self.res) + self.min_x
        wy = (gy * self.res) + self.min_y
        return wx, wy

    def is_blocked(self, gx, gy):
        if not (0 <= gx < self.width and 0 <= gy < self.height):
            return True
        return self.grid[gx, gy]


def heuristic(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def astar(grid_map, start, goal):
    def nearest_free(node, max_radius=18):
        if not grid_map.is_blocked(*node):
            return node
        nx, ny = node
        for radius in range(1, max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    cand = (nx + dx, ny + dy)
                    if not grid_map.is_blocked(*cand):
                        return cand
        return None

    start_node = grid_map.world_to_grid(start[0], start[1])
    goal_node = grid_map.world_to_grid(goal[0], goal[1])

    start_node = nearest_free(start_node)
    goal_node = nearest_free(goal_node)

    if start_node is None or goal_node is None:
        return []

    open_set = []
    heapq.heappush(open_set, (0, start_node))
    came_from = {}
    g_score = {start_node: 0}

    while open_set:
        current = heapq.heappop(open_set)[1]

        if current == goal_node:
            path = []
            while current in came_from:
                path.append(grid_map.grid_to_world(*current))
                current = came_from[current]
            return path[::-1]

        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            neighbor = (current[0] + dx, current[1] + dy)

            if grid_map.is_blocked(*neighbor):
                continue

            tentative_g = g_score[current] + math.sqrt(dx * dx + dy * dy)

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor, goal_node)
                heapq.heappush(open_set, (f, neighbor))

    return []


# --- DRONE STATE ---
class DroneState:
    def __init__(self):
        self.lat = 0.0
        self.lon = 0.0
        self.rel_alt = 0.0
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.yaw = 0.0
        self.roll = 0.0
        self.pitch = 0.0
        self.armed = False
        self.in_air = False
        self.mode = "UNKNOWN"

        # ── Battery (MAVSDK only unless synthetic models are explicitly enabled) ──
        self.battery_voltage_v      = None   # volts
        self.battery_remaining_pct  = None   # 0–100
        self.battery_current_a      = None   # amps

        # ── Angular rates (from MAVSDK IMU, deg/s) ──────────────────────────
        self.roll_rate_dps  = 0.0
        self.pitch_rate_dps = 0.0
        self.yaw_rate_dps   = 0.0

        # ── IMU linear acceleration (body FRD frame, m/s²) ──────────────────
        self.accel_x_ms2    = 0.0    # forward
        self.accel_y_ms2    = 0.0    # right
        self.accel_z_ms2    = 9.81   # down (gravity at rest)
        self.imu_temp_deg_c = 25.0

        # ── GPS quality ─────────────────────────────────────────────────────
        self.gps_fix_type   = 0      # 0=none, 3=3D, 6=RTK-fixed
        self.gps_num_sats   = 0
        self.gps_hdop       = 99.9
        self.altitude_msl_m = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# REALISTIC PHYSICS MODELS  (battery · wind · environment)
# ══════════════════════════════════════════════════════════════════════════════

def isa_temperature(alt_m: float) -> float:
    """ISA standard atmosphere temperature (°C)."""
    return 15.0 - 6.5 * max(0.0, alt_m) / 1000.0


def isa_density(alt_m: float) -> float:
    """ISA air density (kg/m³)."""
    T_K = 288.15 - 6.5 * max(0.0, alt_m) / 1000.0
    return 1.225 * (T_K / 288.15) ** 4.256


class BatteryModel:
    """Physics-based 4S LiPo battery model for DJI X500-class quadrotor.

    Spec : 4S  5 000 mAh  74 Wh usable  14.8 V nominal  16.8 V full
    Power: P  = P_hover + K_aero*v² + m*g*v_climb/η + P_avionics
    Model: discharge curve · internal-resistance voltage sag · current integration
    """
    CAPACITY_AH = 5.0
    CELLS       = 4
    V_FULL      = 4.20 * 4      # 16.8 V
    V_NOMINAL   = 3.70 * 4      # 14.8 V
    V_CUTOFF    = 3.30 * 4      # 13.2 V  (hard cutoff)
    R_INT       = 0.022         # Ω  internal resistance (4S pack)
    MASS_KG     = 1.5           # X500 AUW
    G           = 9.81
    P_HOVER     = 108.0         # W  empirical hover power X500-class
    K_AERO      = 0.55          # W·s²/m²  aerodynamic drag: P_drag = K_AERO*v²
    P_AVIONICS  = 8.0           # W  constant electronics draw
    ETA_CLIMB   = 0.72          # motor+prop efficiency for climb

    def __init__(self):
        self.soc              = 1.0   # state of charge [0, 1]
        self.energy_consumed_wh = 0.0

    @property
    def voltage(self) -> float:
        """Open-circuit voltage from SoC (simplified piecewise)."""
        return max(self.V_CUTOFF,
                   self.V_FULL - (1.0 - self.soc) * (self.V_FULL - self.V_CUTOFF))

    @property
    def remaining_pct(self) -> float:
        return self.soc * 100.0

    def power_draw(self, vx: float, vy: float, vz: float) -> float:
        """Estimate instantaneous power (W) from NED velocity."""
        v_h    = math.sqrt(vx**2 + vy**2)
        climb  = max(0.0, -vz)                               # NED: up = negative vz
        p_aero  = self.K_AERO * v_h**2
        p_climb = self.MASS_KG * self.G * climb / self.ETA_CLIMB
        return self.P_HOVER + p_aero + p_climb + self.P_AVIONICS

    def step(self, vx: float, vy: float, vz: float, dt_s: float):
        """Advance one time step. Returns (current_a, power_w)."""
        if dt_s <= 0:
            return 0.0, 0.0
        p   = self.power_draw(vx, vy, vz)
        v   = max(self.voltage, 12.0)
        i   = p / v
        dah = i * dt_s / 3600.0
        self.soc = max(0.0, self.soc - dah / self.CAPACITY_AH)
        self.energy_consumed_wh += p * dt_s / 3600.0
        return i, p

    def flight_time_remaining(self, vx: float, vy: float, vz: float) -> float:
        """Estimated remaining airborne time (s) at current draw."""
        p = max(1.0, self.power_draw(vx, vy, vz))
        wh_left = self.soc * self.CAPACITY_AH * self.voltage / 1000.0
        return wh_left / p * 3600.0


class WindModel:
    """Ornstein-Uhlenbeck wind simulation in NED frame.

    Generates correlated, slowly varying wind with realistic gusts.
    Typical range: 0–8 m/s with max gusts ~13 m/s.
    """
    THETA = 0.04   # mean-reversion rate  (s⁻¹)
    SIGMA = 0.18   # volatility per √s    (m/s/√s)
    MU_N  = 0.0    # long-term mean north  (m/s)
    MU_E  = 0.0    # long-term mean east   (m/s)

    def __init__(self, seed: int | None = None):
        rng = random.Random(seed)
        self.north = rng.gauss(1.5, 1.2)
        self.east  = rng.gauss(0.5, 1.2)
        self.up    = 0.0
        self._rng  = rng

    def step(self, dt_s: float) -> None:
        sq = math.sqrt(max(dt_s, 0.0))
        self.north += self.THETA * (self.MU_N - self.north) * dt_s + self.SIGMA * sq * self._rng.gauss(0, 1)
        self.east  += self.THETA * (self.MU_E - self.east)  * dt_s + self.SIGMA * sq * self._rng.gauss(0, 1)
        self.north = max(-14.0, min(14.0, self.north))
        self.east  = max(-14.0, min(14.0, self.east))

    @property
    def speed(self) -> float:
        return math.sqrt(self.north**2 + self.east**2)

    @property
    def direction_deg(self) -> float:
        """Wind-FROM direction, meteorological convention (°True)."""
        return (math.degrees(math.atan2(-self.east, -self.north)) + 360) % 360


# ══════════════════════════════════════════════════════════════════════════════
# ENRICHED TELEMETRY LISTENERS
# ══════════════════════════════════════════════════════════════════════════════

async def battery_listener(drone, state):
    """Read battery voltage and remaining % from MAVSDK."""
    try:
        async for batt in drone.telemetry.battery():
            if batt.voltage_v is not None:
                state.battery_voltage_v = float(batt.voltage_v)
            rp = batt.remaining_percent
            if rp is not None:
                # MAVSDK versions differ: some 0..1, some 0..100
                state.battery_remaining_pct = float(rp * 100.0) if rp <= 1.0 else float(rp)
    except Exception:
        pass


async def imu_listener(drone, state):
    """Read IMU angular rates + linear acceleration from MAVSDK."""
    try:
        async for imu in drone.telemetry.imu():
            av = imu.angular_velocity_frd
            if av is not None:
                state.roll_rate_dps  = math.degrees(float(av.forward_rad_s))
                state.pitch_rate_dps = math.degrees(float(av.right_rad_s))
                state.yaw_rate_dps   = math.degrees(float(av.down_rad_s))
            accel = imu.acceleration_frd
            if accel is not None:
                state.accel_x_ms2 = float(accel.forward_m_s2)
                state.accel_y_ms2 = float(accel.right_m_s2)
                state.accel_z_ms2 = float(accel.down_m_s2)
            if hasattr(imu, 'temperature_degc') and imu.temperature_degc is not None:
                state.imu_temp_deg_c = float(imu.temperature_degc)
    except Exception:
        pass


async def gps_quality_listener(drone, state):
    """Read GPS fix type and satellite count."""
    try:
        async for gps_info in drone.telemetry.gps_info():
            state.gps_num_sats = int(gps_info.num_satellites)
            ft = gps_info.fix_type
            state.gps_fix_type = int(ft.value) if hasattr(ft, 'value') else int(ft)
    except Exception:
        pass


async def raw_gps_listener(drone, state):
    """Read HDOP and MSL altitude from raw GPS."""
    try:
        async for raw in drone.telemetry.raw_gps():
            if raw.hdop is not None:
                state.gps_hdop = float(raw.hdop)
            alt = getattr(raw, 'absolute_altitude_m', None)
            if alt is not None:
                state.altitude_msl_m = float(alt)
    except Exception:
        pass


async def apply_demo_px4_params(drone) -> None:
    """Best-effort PX4 parameter tuning for SITL/app-control demos."""
    candidates = [
        ("COM_ARM_WO_GPS", 1, "int"),
        ("COM_DISARM_PRFLT", 60.0, "float"),
        ("COM_PREARM_MODE", 0, "int"),
    ]
    for name, value, kind in candidates:
        try:
            if kind == "int":
                await drone.param.set_param_int(name, int(value))
            else:
                await drone.param.set_param_float(name, float(value))
            log(f"--> PX4 param applied: {name}={value}")
        except Exception as exc:
            log(f"!! PX4 param skipped ({name}): {exc}")


# --- LISTENERS ---
async def telemetry_listener(drone, state):
    async for pos in drone.telemetry.position():
        state.lat = pos.latitude_deg
        state.lon = pos.longitude_deg
        state.rel_alt = pos.relative_altitude_m


async def velocity_listener(drone, state):
    async for vel in drone.telemetry.velocity_ned():
        state.vx = vel.north_m_s
        state.vy = vel.east_m_s
        state.vz = vel.down_m_s


async def local_pos_listener(drone, state):
    async for pv in drone.telemetry.position_velocity_ned():
        state.x = pv.position.north_m
        state.y = pv.position.east_m
        state.z = pv.position.down_m
        state.vx = pv.velocity.north_m_s
        state.vy = pv.velocity.east_m_s
        state.vz = pv.velocity.down_m_s


async def att_listener(drone, state):
    async for angle in drone.telemetry.heading():
        state.yaw = angle.heading_deg


async def att_euler_listener(drone, state):
    try:
        async for euler in drone.telemetry.attitude_euler():
            state.roll = float(euler.roll_deg)
            state.pitch = float(euler.pitch_deg)
    except Exception:
        # Keep running without Euler telemetry if not available on this platform.
        pass


async def armed_listener(drone, state):
    try:
        async for armed in drone.telemetry.armed():
            state.armed = bool(armed)
    except Exception:
        pass


async def in_air_listener(drone, state):
    try:
        async for in_air in drone.telemetry.in_air():
            state.in_air = bool(in_air)
    except Exception:
        pass


async def flight_mode_listener(drone, state):
    try:
        async for mode in drone.telemetry.flight_mode():
            state.mode = str(mode)
    except Exception:
        pass


async def redis_telemetry_pump(redis_client, state, drone_id: str):
    while True:
        telemetry_data = {
            "drone_id": drone_id,
            "latitude": state.lat,
            "longitude": state.lon,
            "altitude": state.rel_alt,
            "heading": state.yaw,
            "speed": math.sqrt(state.vx**2 + state.vy**2),
            "battery": 99.0,
            "armed": state.armed,
            "in_air": state.in_air,
            "mode": state.mode or "TEACHER_BRIDGE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await redis_client.publish('telemetry', json.dumps(telemetry_data))
        except Exception:
            pass
        await asyncio.sleep(0.25)


# --- MAIN (ONLINE) ---
async def collect_data(args):
    """ONLINE MODE: PX4 + Gazebo + MAVSDK."""

    if System is None:
        raise RuntimeError("MAVSDK not available in this environment. Use --offline.")

    log("--> Starting teacher (ONLINE)...")

    # Ensure the output path exists early so runs always leave an auditable artifact,
    # even if MAVSDK connection fails before the first telemetry row is written.
    try:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.touch(exist_ok=True)
    except Exception:
        pass

    world_map = Map(args.sdf_path)
    log("--> Map loaded.")
    grid = GridMap(world_map.obstacles, resolution=1.0, margin=2.5)
    log("--> Grid ready.")

    # --- Redis Setup (Bridge) ---
    redis_client = None
    redis_pubsub = None
    
    if redis:
        try:
            redis_client = redis.Redis(host=args.redis_host, port=args.redis_port, db=0)
            await redis_client.ping()
            # Subscribe to commands
            redis_pubsub = redis_client.pubsub()
            await redis_pubsub.subscribe('commands')
            log(f"--> Redis connected (Bridge Established) at {args.redis_host}:{args.redis_port}")
        except Exception as e:
            log(f"!! Redis Bridge Failed: {e}")
            redis_client = None

    # If mavsdk_server is set to 'auto', let mavsdk-python manage/spawn it.
    if (args.mavsdk_server or '').strip().lower() in ('auto', ''):
        drone = System()
    else:
        drone = System(
            mavsdk_server_address=args.mavsdk_server,
            port=args.mavsdk_port,
        )
    addr = args.system
    if "://" not in addr:
        addr = f"udpin://{addr}"
    log(f"--> Connecting to {addr}...")
    try:
        await asyncio.wait_for(drone.connect(system_address=addr), timeout=10)
    except asyncio.TimeoutError:
        raise RuntimeError("MAVSDK connect() timed out. Is PX4 running and reachable?")
    except Exception as e:
        log(f"!! connect() failed: {e}")
        raise

    log("--> Waiting for drone (timeout 30s)...")
    start_wait = time.time()
    try:
        async for s in drone.core.connection_state():
            if s.is_connected:
                log("--> Connected!")
                break
            if time.time() - start_wait > 30:
                raise RuntimeError(
                    "Timed out waiting for PX4. Check MAVLink UDP reachability and PX4 is running."
                )
    except Exception as e:
        log(f"!! connection_state failed: {e}")
        raise

    await apply_demo_px4_params(drone)

    dstate = DroneState()
    asyncio.create_task(telemetry_listener(drone, dstate))
    asyncio.create_task(local_pos_listener(drone, dstate))
    asyncio.create_task(att_listener(drone, dstate))
    asyncio.create_task(att_euler_listener(drone, dstate))
    asyncio.create_task(armed_listener(drone, dstate))
    asyncio.create_task(in_air_listener(drone, dstate))
    asyncio.create_task(flight_mode_listener(drone, dstate))
    asyncio.create_task(battery_listener(drone, dstate))
    asyncio.create_task(imu_listener(drone, dstate))
    asyncio.create_task(gps_quality_listener(drone, dstate))
    asyncio.create_task(raw_gps_listener(drone, dstate))
    if redis_client:
        asyncio.create_task(redis_telemetry_pump(redis_client, dstate, args.drone_id))

    if not args.bridge_only:
        await asyncio.sleep(2)
        print("--> Arming...")
        try:
            await drone.action.arm()
            await drone.action.set_takeoff_altitude(args.alt)
            await drone.action.takeoff()
            await asyncio.sleep(8)
        except Exception as e:
            print(f"Arm/Takeoff failed: {e}")

    # Prefer local NED position (stable in SITL) over GPS-derived xy.
    # Wait briefly until local position starts updating.
    start_lp = time.time()
    while time.time() - start_lp < 10.0 and (dstate.x == 0.0 and dstate.y == 0.0):
        await asyncio.sleep(0.05)

    def get_local_pos():
        return ned_to_map_xy(dstate.x, dstate.y)

    offboard_active = False

    async def ensure_offboard_started():
        nonlocal offboard_active
        warmup_hz = max(5.0, float(args.hz))

        async def _warmup(duration_s: float):
            warmup_count = int(warmup_hz * duration_s)
            for _ in range(max(1, warmup_count)):
                await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, dstate.yaw))
                await asyncio.sleep(1.0 / warmup_hz)

        await _warmup(1.0)
        try:
            await drone.offboard.start()
        except OffboardError as e:
            text = str(e).lower()
            if 'already started' in text:
                offboard_active = True
                return
            if 'no setpoint set' in text:
                await _warmup(2.0)
                await drone.offboard.start()
            else:
                raise
        offboard_active = True

    if args.bridge_only:
        print("--> Control bridge mode active; awaiting app commands...")
    else:
        print("--> Starting A* Pathfinding (ONLINE)...")
        try:
            await ensure_offboard_started()
        except OffboardError as e:
            log(f"!! Initial offboard start failed (continuing without offboard): {e}")
            offboard_active = False

    takeoff_target_alt = None

    async def arm_vehicle_best_effort(context: str) -> bool:
        if dstate.armed:
            return True
        try:
            await drone.action.arm()
            await asyncio.sleep(1.5)
            return True
        except Exception as exc:
            if 'COMMAND_DENIED' in str(exc).upper():
                log(f"!! {context} arm denied, re-applying demo PX4 params and retrying once...")
                try:
                    await apply_demo_px4_params(drone)
                    await asyncio.sleep(0.25)
                    await drone.action.arm()
                    await asyncio.sleep(1.5)
                    return True
                except Exception as retry_exc:
                    log(f"!! {context} arm retry failed: {retry_exc}")
                    return False
            log(f"!! {context} arm failed: {exc}")
            return False

    async def trigger_takeoff_best_effort(target_alt: float, context: str) -> bool:
        target_alt = max(1.5, float(target_alt))
        if not await arm_vehicle_best_effort(context):
            return False
        try:
            await drone.action.set_takeoff_altitude(target_alt)
        except Exception:
            pass
        try:
            await drone.action.takeoff()
            await asyncio.sleep(1.0)
            return True
        except Exception as exc:
            if 'COMMAND_DENIED' in str(exc).upper():
                log(f"!! {context} takeoff denied, re-applying demo PX4 params and retrying once...")
                try:
                    await apply_demo_px4_params(drone)
                    await asyncio.sleep(0.25)
                    try:
                        await drone.action.set_takeoff_altitude(target_alt)
                    except Exception:
                        pass
                    await drone.action.takeoff()
                    await asyncio.sleep(1.0)
                    return True
                except Exception as retry_exc:
                    log(f"!! {context} takeoff retry failed: {retry_exc}")
                    return False
            log(f"!! {context} takeoff failed: {exc}")
            return False

    f = open(args.out, "w", newline="", encoding="utf-8")
    writer = csv.writer(f)

    # Segmentation log: lidar-derived obstacle detections surfaced in the app's Analytics feed
    _seg_log_dir = Path("logs")
    _seg_log_dir.mkdir(parents=True, exist_ok=True)
    _seg_log_date = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    seg_log_f = open(_seg_log_dir / f"seg_diag_{_seg_log_date}.csv", "w", newline="", encoding="utf-8")
    seg_log_writer = csv.writer(seg_log_f)
    seg_log_writer.writerow(["drone_id", "detected_class", "confidence", "timestamp"])
    seg_log_f.flush()

    header = [
        # ───── original 24 columns ─────
        "timestamp",
        "lat",
        "lon",
        "rel_alt",
        "vx",
        "vy",
        "vz",
        "yaw",
        "cmd_vx",
        "cmd_vy",
        "cmd_vz",
        "cmd_yaw",
        "lidar_min",
        "front_lidar_min",
        "cross_track_m",
        "heading_error_deg",
        "sideslip_deg",
        "progress_mps",
        "geom_clearance_m",
        "geom_threat",
        "tilt_target_deg",
        "lidar_json",
        "goal_x",
        "goal_y",
        # ───── new 34 enriched columns ─────
        # attitude
        "roll_deg",
        "pitch_deg",
        # angular rates
        "roll_rate_dps",
        "pitch_rate_dps",
        "yaw_rate_dps",
        # body accelerations
        "accel_fwd_ms2",
        "accel_right_ms2",
        "accel_down_ms2",
        # battery / power
        "battery_voltage_v",
        "battery_current_a",
        "battery_remaining_pct",
        "power_draw_w",
        "energy_consumed_wh",
        "flight_time_remaining_s",
        # wind / environment
        "wind_north_mps",
        "wind_east_mps",
        "wind_speed_mps",
        "wind_dir_deg",
        "temperature_deg_c",
        "air_density_kg_m3",
        # navigation
        "ground_speed_mps",
        "course_over_ground_deg",
        "distance_to_goal_m",
        "path_wps_remaining",
        "mission_elapsed_s",
        "total_distance_flown_m",
        "flight_phase",
        # GPS quality
        "gps_fix_type",
        "gps_num_sats",
        "gps_hdop",
        "altitude_msl_m",
        # obstacle / airspeed
        "obstacle_count_near",
        "effective_airspeed_mps",
        # flags
        "is_replanning",
        "is_recovering",
    ]
    writer.writerow(header)

    start_time = time.time()
    last_step = time.time()
    run_forever = float(args.duration) <= 0.0

    # ── Environment/physics simulation policy ───────────────────────────────────────
    # We keep *environment stressors* (e.g., wind) available for realism/training,
    # but we do NOT fabricate system-result telemetry (e.g., battery %) by default.
    enable_synthetic_models = bool(getattr(args, 'enable_synthetic_models', False))
    disable_wind_model = bool(getattr(args, 'disable_wind_model', False))
    enable_battery_model = bool(getattr(args, 'enable_battery_model', False))
    if enable_synthetic_models:
        enable_battery_model = True
        disable_wind_model = False

    wind_model = None if disable_wind_model else WindModel()
    battery_model = BatteryModel() if enable_battery_model else None
    total_distance_m   = 0.0
    last_logged_px, last_logged_py = 0.0, 0.0
    airborne_since  = None   # set once the drone first lifts off
    _is_replanning  = False
    _is_recovering  = False

    # Command smoothing / limits (stability)
    prev_vx_cmd = 0.0
    prev_vy_cmd = 0.0
    prev_fwd_cmd = 0.0
    prev_lat_cmd = 0.0
    max_accel_world = 3.5  # m/s^2
    max_accel_body = 4.0  # m/s^2

    # Safety shaping
    if args.precision_mode:
        slow_down_dist = 5.5
        hard_stop_dist = 1.6
    else:
        slow_down_dist = 8.0
        hard_stop_dist = 2.8
    metrics_log_at = time.time()

    current_path = []
    path_index = 0
    goal_x, goal_y = 0, 0
    external_mission = None
    recent_goals = deque(maxlen=5)

    # Anti-loiter watchdog (strike-based to avoid false replans while turning/braking)
    last_progress_check = time.time()
    progress_anchor = (0.0, 0.0)
    low_progress_strikes = 0
    heading_stall_strikes = 0
    last_heading_err_abs = 0.0
    last_front_min_dist = 20.0
    last_geom_clearance_m = 20.0
    front_min_filtered = 20.0
    front_blocked_since = None
    threat_trigger_since = None
    goal_set_at = time.time()
    last_replan_at = 0.0
    unstable_since = None
    recovery_until = 0.0
    last_recovery_log = 0.0

    def pick_new_goal():
        curr_x, curr_y = get_local_pos()
        best = None
        best_score = -1e9
        for _ in range(200):
            gx = np.random.randint(10, grid.width - 10)
            gy = np.random.randint(10, grid.height - 10)
            if grid.is_blocked(gx, gy):
                continue
            wx, wy = grid.grid_to_world(gx, gy)
            dist = math.sqrt((wx - curr_x) ** 2 + (wy - curr_y) ** 2)
            if dist < 45.0:
                continue

            nearest_recent = min(
                [math.sqrt((wx - rx) ** 2 + (wy - ry) ** 2) for rx, ry in recent_goals],
                default=999.0,
            )
            # Prefer farther goals and avoid recently visited areas.
            score = dist + (0.35 * nearest_recent)
            if score > best_score:
                best_score = score
                best = (wx, wy)

        if best is not None:
            recent_goals.append(best)
            return best

        # Safe fallback when map is constrained
        while True:
            gx = np.random.randint(10, grid.width - 10)
            gy = np.random.randint(10, grid.height - 10)
            if not grid.is_blocked(gx, gy):
                wx, wy = grid.grid_to_world(gx, gy)
                if math.sqrt((wx - curr_x) ** 2 + (wy - curr_y) ** 2) > 25.0:
                    recent_goals.append((wx, wy))
                    return wx, wy

    def set_goal_from_global(target_lat: float, target_lon: float):
        nonlocal goal_x, goal_y, goal_set_at, current_path, path_index
        lat0, lon0 = dstate.lat, dstate.lon
        cur_map_x, cur_map_y = get_local_pos()
        d_lat = target_lat - lat0
        d_lon = target_lon - lon0
        d_north = d_lat * 111319.0
        d_east = d_lon * 111319.0 * math.cos(math.radians(lat0))
        d_map_x, d_map_y = ned_to_map_xy(d_north, d_east)
        goal_x, goal_y = cur_map_x + d_map_x, cur_map_y + d_map_y
        goal_set_at = time.time()
        current_path = []
        path_index = 0

    def stop_external_mission(log_message: str | None = None):
        nonlocal external_mission, current_path, path_index, goal_x, goal_y, goal_set_at
        external_mission = None
        px_now, py_now = get_local_pos()
        goal_x, goal_y = px_now, py_now
        goal_set_at = time.time()
        current_path = [(px_now, py_now)]
        path_index = 0
        if log_message:
            log(log_message)

    if args.bridge_only:
        goal_x, goal_y = get_local_pos()
        goal_set_at = time.time()
        progress_anchor = get_local_pos()
    else:
        goal_x, goal_y = pick_new_goal()
        goal_set_at = time.time()
        progress_anchor = get_local_pos()
        print(f"First Goal: {goal_x:.1f}, {goal_y:.1f}")

    try:
        while True:
            elapsed = time.time() - start_time
            if (not run_forever) and (elapsed > float(args.duration)):
                break

            now = time.time()
            dt = now - last_step
            period = 1.0 / max(1.0, float(args.hz))
            if dt < period:
                await asyncio.sleep(max(0.0, period - dt))
                continue
            last_step = now

            # ── Environment + optional battery model ────────────────────────────
            _batt_i = None
            _batt_p = None
            if wind_model is not None:
                wind_model.step(dt)
            if battery_model is not None:
                _batt_i, _batt_p = battery_model.step(dstate.vx, dstate.vy, dstate.vz, dt)
                # Battery model outputs are logged in CSV as model fields, but we do NOT
                # publish/override main battery telemetry unless MAVSDK provides it.
                dstate.battery_current_a = _batt_i
            # Airborne timer
            if dstate.in_air and airborne_since is None:
                airborne_since = time.time()

            px, py = get_local_pos()
            # Odometer
            _d = math.sqrt((px - last_logged_px)**2 + (py - last_logged_py)**2)
            if _d < 10.0:
                total_distance_m += _d
            last_logged_px, last_logged_py = px, py

            if (
                args.bridge_only
                and external_mission
                and external_mission.get("status") == "ACTIVE"
                and external_mission.get("await_takeoff_alt") is not None
            ):
                target_alt = float(external_mission.get("await_takeoff_alt") or 0.0)
                # Only transition to offboard navigation once the drone has physically climbed
                # to near the target altitude via PX4 auto-takeoff.  Using dstate.in_air alone
                # is unreliable – PX4 SITL reports in_air=True almost immediately after the
                # takeoff command even when the drone is still on the ground, which would
                # prematurely cancel AUTO.TAKEOFF and lock the drone at ground level in OFFBOARD
                # mode with vz=0.  Require rel_alt to be within 1.5 m of the target altitude.
                if dstate.rel_alt >= max(2.0, target_alt - 1.5):
                    try:
                        if not offboard_active:
                            await ensure_offboard_started()
                    except Exception as mission_offboard_exc:
                        log(f"!! Mission offboard start warning: {mission_offboard_exc}")
                    wp = external_mission["waypoints"][external_mission["current_idx"]]
                    set_goal_from_global(float(wp[0]), float(wp[1]))
                    external_mission["await_takeoff_alt"] = None
                    log(f"--> External mission navigation engaged for waypoint {external_mission['current_idx'] + 1}")

            # If not making meaningful progress, consider replanning using guarded strike logic.
            if (not args.bridge_only) and now - last_progress_check > float(args.progress_window_sec):
                moved = math.sqrt((px - progress_anchor[0]) ** 2 + (py - progress_anchor[1]) ** 2)
                in_goal_grace = (now - goal_set_at) < float(args.goal_grace_sec)
                turning_in_place = last_heading_err_abs > float(args.replan_heading_hold_deg)
                obstacle_braking = (last_front_min_dist < (hard_stop_dist + 0.5)) or (
                    last_geom_clearance_m < (hard_stop_dist + 0.7)
                )

                if moved < float(args.min_progress_m) and not in_goal_grace and not turning_in_place and not obstacle_braking:
                    low_progress_strikes += 1
                    log(
                        "Low progress strike "
                        f"{low_progress_strikes}/{int(args.replan_strikes)} "
                        f"(moved={moved:.2f}m, head_err={last_heading_err_abs:.1f}deg, "
                        f"front={last_front_min_dist:.2f}m, geom={last_geom_clearance_m:.2f}m)"
                    )
                else:
                    low_progress_strikes = 0

                if low_progress_strikes >= int(args.replan_strikes):
                    if (now - last_replan_at) >= float(args.replan_cooldown_sec):
                        print("Low progress persisted -> replanning with a new goal")
                        goal_x, goal_y = pick_new_goal()
                        goal_set_at = time.time()
                        last_replan_at = now
                        current_path = []
                        low_progress_strikes = 0
                progress_anchor = (px, py)
                last_progress_check = now

            if not current_path or path_index >= len(current_path):
                if args.bridge_only and takeoff_target_alt is None and not (external_mission and external_mission.get("status") == "ACTIVE"):
                    goal_x, goal_y = px, py
                    current_path = [(px, py)]
                    path_index = 0
                else:
                    print(f"Planning A* to {goal_x:.0f},{goal_y:.0f}...")
                    path = astar(grid, (px, py), (goal_x, goal_y))
                    if not path:
                        print("Path failed! Picking new goal.")
                        goal_x, goal_y = pick_new_goal()
                        goal_set_at = time.time()
                        continue

                    # Downsample less aggressively for smoother guidance.
                    stride = 2 if args.precision_mode else 3
                    current_path = path[::stride] + [path[-1]]
                    path_index = 0

                    # Validate that no waypoint in the downsampled path grazes
                    # an obstacle within the safety margin.  If the path is
                    # compromised, request a fresh replan immediately.
                    path_clear = True
                    for _wp in current_path:
                        for _obs in world_map.obstacles:
                            if _obs.distance_to_point(_wp[0], _wp[1]) < float(args.obstacle_safety_margin_m):
                                path_clear = False
                                break
                        if not path_clear:
                            break
                    if not path_clear:
                        print("Path grazes obstacle — replanning to safer goal.")
                        goal_x, goal_y = pick_new_goal()
                        goal_set_at = time.time()
                        last_replan_at = now
                        current_path = []
                        continue

                    print(f"Path found! {len(current_path)} waypoints")

            speed_now = math.sqrt(dstate.vx * dstate.vx + dstate.vy * dstate.vy)
            if args.precision_mode:
                lookahead_dist = clamp(8.0 + (1.2 * speed_now), 8.0, 22.0)
            else:
                lookahead_dist = clamp(6.0 + (0.8 * speed_now), 6.0, 18.0)
            target_pt = current_path[path_index]

            for i in range(path_index, len(current_path)):
                pt = current_path[i]
                d = math.sqrt((pt[0] - px) ** 2 + (pt[1] - py) ** 2)
                if d > lookahead_dist:
                    target_pt = pt
                    path_index = i
                    break

                if i == len(current_path) - 1 and d < 2.0:
                    if args.bridge_only:
                        if external_mission and external_mission.get("status") == "ACTIVE":
                            # Don't advance while the drone is still climbing to takeoff altitude.
                            # The initial current_path = [(px0, py0)] would otherwise trigger an
                            # immediate "goal reached" false-positive before the drone has moved.
                            if external_mission.get("await_takeoff_alt") is not None:
                                pass  # still climbing – hold current waypoint index
                            elif external_mission["current_idx"] + 1 < len(external_mission["waypoints"]):
                                external_mission["current_idx"] += 1
                                wp = external_mission["waypoints"][external_mission["current_idx"]]
                                set_goal_from_global(float(wp[0]), float(wp[1]))
                                log(f"--> External mission advanced to waypoint {external_mission['current_idx'] + 1}/{len(external_mission['waypoints'])}")
                            else:
                                stop_external_mission("--> External mission completed")
                        else:
                            current_path = [(px, py)]
                            path_index = 0
                            goal_x, goal_y = px, py
                    else:
                        print("Goal Reached! New Goal...")
                        goal_x, goal_y = pick_new_goal()
                        goal_set_at = time.time()
                        current_path = []
                    break

            if not current_path:
                continue

            tx, ty = target_pt
            dx = tx - px
            dy = ty - py
            dist = math.sqrt(dx * dx + dy * dy)

            # Path tangent and signed cross-track error (map frame).
            if path_index > 0:
                prev_pt = current_path[path_index - 1]
            else:
                prev_pt = (px, py)
            seg_dx = tx - prev_pt[0]
            seg_dy = ty - prev_pt[1]
            seg_len = math.sqrt(seg_dx * seg_dx + seg_dy * seg_dy)
            if seg_len < 1e-6 and dist > 1e-6:
                seg_dx, seg_dy, seg_len = dx, dy, dist
            if seg_len > 1e-6:
                seg_ux = seg_dx / seg_len
                seg_uy = seg_dy / seg_len
                rx = px - prev_pt[0]
                ry = py - prev_pt[1]
                cross_track_m = (rx * seg_uy) - (ry * seg_ux)
            else:
                cross_track_m = 0.0

            map_yaw_deg = heading_to_map_yaw(dstate.yaw)
            sim_lidar = world_map.simulate_lidar(px, py, dstate.rel_alt, map_yaw_deg)
            min_dist = float(np.min(sim_lidar))

            map_vx_now, map_vy_now = ned_to_map_xy(dstate.vx, dstate.vy)
            yaw_rad_now = math.radians(map_yaw_deg)
            c_now = math.cos(yaw_rad_now)
            s_now = math.sin(yaw_rad_now)
            v_forward_now = (map_vx_now * c_now) + (map_vy_now * s_now)
            v_lateral_now = (-map_vx_now * s_now) + (map_vy_now * c_now)
            sideslip_now_deg = math.degrees(math.atan2(v_lateral_now, max(0.3, abs(v_forward_now))))

            num_rays = len(sim_lidar)
            front_center = num_rays // 2
            front_half_window = max(2, int(round(num_rays * max(5.0, float(args.obstacle_sector_deg / 2.0)) / 360.0)))
            front_slice = sim_lidar[
                max(0, front_center - front_half_window) : min(num_rays, front_center + front_half_window + 1)
            ]
            front_min_raw = float(np.min(front_slice)) if len(front_slice) else min_dist

            _rux = (dx / dist) if dist > 1e-6 else 0.0
            _ruy = (dy / dist) if dist > 1e-6 else 0.0
            avoid_x, avoid_y, geom_clearance_m, geom_threat = world_map.obstacle_avoidance_field(
                px,
                py,
                dstate.rel_alt,
                map_yaw_deg,
                route_ux=_rux,
                route_uy=_ruy,
                lookahead_m=float(args.obstacle_lookahead_m),
                corridor_deg=float(args.obstacle_corridor_deg),
                safety_margin_m=float(args.obstacle_safety_margin_m),
                vertical_clearance_m=float(args.obstacle_height_clearance_m),
            )

            # Proactive threat-triggered replan: when the avoidance field
            # reports a sustained high threat (obstacle in our path that A*
            # didn't fully clear), replan immediately rather than waiting for
            # the stall-strike counter to accumulate.
            if geom_threat >= 0.85:
                if threat_trigger_since is None:
                    threat_trigger_since = now
                elif (
                    (now - threat_trigger_since) >= 0.5
                    and (now - last_replan_at) >= float(args.replan_cooldown_sec)
                    and not (args.bridge_only and external_mission and external_mission.get("status") == "ACTIVE")
                ):
                    print(f"High obstacle threat ({geom_threat:.2f}) → proactive replan")
                    path = astar(grid, (px, py), (goal_x, goal_y))
                    if path:
                        stride = 2 if args.precision_mode else 3
                        current_path = path[::stride] + [path[-1]]
                        path_index = 0
                    last_replan_at = now
                    threat_trigger_since = None
            else:
                threat_trigger_since = None
            last_geom_clearance_m = geom_clearance_m

            # Front-distance robustness: reject clear sensor artifacts and debounce hard-stop decisions.
            likely_front_glitch = (
                front_min_raw <= float(args.front_zero_glitch_threshold_m)
                and geom_clearance_m >= float(args.front_zero_ignore_geom_clear_m)
                and geom_threat <= float(args.front_zero_ignore_geom_threat)
            )
            if likely_front_glitch:
                front_min_dist = max(front_min_filtered, hard_stop_dist + 1.0, geom_clearance_m)
            else:
                front_min_dist = front_min_raw

            front_min_filtered = (
                float(args.front_filter_alpha) * front_min_filtered
                + (1.0 - float(args.front_filter_alpha)) * front_min_dist
            )
            front_eval_dist = min(front_min_dist, front_min_filtered)
            last_front_min_dist = front_eval_dist

            if front_eval_dist < hard_stop_dist:
                if front_blocked_since is None:
                    front_blocked_since = now
            elif front_eval_dist > (hard_stop_dist + float(args.front_recover_margin_m)):
                front_blocked_since = None

            front_blocked_persisted = (
                front_blocked_since is not None
                and (now - front_blocked_since) >= float(args.front_block_debounce_sec)
            )

            route_ux = (dx / dist) if dist > 1e-6 else 0.0
            route_uy = (dy / dist) if dist > 1e-6 else 0.0
            avoid_norm = math.hypot(avoid_x, avoid_y)
            if avoid_norm > 1e-6:
                avoid_ux = avoid_x / avoid_norm
                avoid_uy = avoid_y / avoid_norm
            else:
                avoid_ux = 0.0
                avoid_uy = 0.0

            # Allow full avoidance override when threat is critical (≥ 0.9);
            # otherwise cap at max_avoidance_blend to preserve route-following.
            if geom_threat >= 0.90:
                avoid_blend = 1.0
            else:
                avoid_blend = clamp(float(args.avoidance_gain) * geom_threat, 0.0, float(args.max_avoidance_blend))
            nav_ux = ((1.0 - avoid_blend) * route_ux) + (avoid_blend * avoid_ux)
            nav_uy = ((1.0 - avoid_blend) * route_uy) + (avoid_blend * avoid_uy)
            nav_norm = math.hypot(nav_ux, nav_uy)
            if nav_norm > 1e-6:
                nav_ux /= nav_norm
                nav_uy /= nav_norm
            else:
                nav_ux, nav_uy = route_ux, route_uy

            # Desired speed: fast cruise with heading-aware taper and true frontal obstacle braking.
            desired_speed = min(float(args.max_speed), max(float(args.base_speed), 0.70 * dist))
            bridge_idle_hold = (
                args.bridge_only
                and takeoff_target_alt is None
                and not (external_mission and external_mission.get("status") == "ACTIVE")
                and abs(goal_x - px) < 0.5
                and abs(goal_y - py) < 0.5
            )
            if bridge_idle_hold:
                desired_speed = 0.0
            if front_eval_dist >= slow_down_dist:
                obstacle_factor = 1.0
            else:
                obstacle_factor = clamp(
                    (front_eval_dist - hard_stop_dist) / max(1e-6, (slow_down_dist - hard_stop_dist)),
                    0.0,
                    1.0,
                )
            yaw_target_nom = (
                map_yaw_deg
                if bridge_idle_hold
                else (
                    math.degrees(math.atan2(nav_uy, nav_ux))
                    if (abs(nav_ux) + abs(nav_uy)) > 1e-6
                    else math.degrees(math.atan2(dy, dx))
                )
            )
            if args.precision_mode:
                yaw_crosstrack_correction = clamp(
                    -args.crosstrack_kp * cross_track_m,
                    -abs(args.crosstrack_heading_cap_deg),
                    abs(args.crosstrack_heading_cap_deg),
                )
            else:
                yaw_crosstrack_correction = 0.0
            yaw_target = wrap_deg(yaw_target_nom + yaw_crosstrack_correction)
            yaw_err_abs = abs(shortest_diff(map_yaw_deg, yaw_target))
            heading_factor = clamp(
                1.0 - (yaw_err_abs / (70.0 if args.precision_mode else 95.0)),
                0.35 if args.precision_mode else 0.25,
                1.0,
            )
            if yaw_err_abs >= float(args.heading_align_stop_deg):
                heading_factor = min(heading_factor, float(args.heading_stop_speed_ratio))
            elif yaw_err_abs >= float(args.heading_align_slow_deg):
                align_span = max(1.0, float(args.heading_align_stop_deg) - float(args.heading_align_slow_deg))
                align_frac = (yaw_err_abs - float(args.heading_align_slow_deg)) / align_span
                heading_factor *= clamp(1.0 - (0.75 * align_frac), float(args.heading_slow_min_ratio), 1.0)

            attitude_soft_deg = max(abs(dstate.roll), abs(dstate.pitch))
            soft_guard_deg = min(float(args.max_roll_guard_deg), float(args.max_pitch_guard_deg)) * float(args.attitude_soft_guard_ratio)
            if attitude_soft_deg > soft_guard_deg:
                excess = attitude_soft_deg - soft_guard_deg
                span = max(1.0, min(float(args.max_roll_guard_deg), float(args.max_pitch_guard_deg)) - soft_guard_deg)
                attitude_factor = clamp(1.0 - (excess / span), float(args.attitude_soft_min_speed_ratio), 1.0)
            else:
                attitude_factor = 1.0
            if args.precision_mode:
                desired_speed *= heading_factor
                desired_speed *= attitude_factor
                if obstacle_factor < 1.0:
                    desired_speed *= obstacle_factor
                if geom_clearance_m < (hard_stop_dist + 1.4):
                    desired_speed *= clamp((geom_clearance_m - hard_stop_dist) / 1.4, 0.2, 1.0)
                if front_min_dist > (hard_stop_dist + 0.7):
                    desired_speed = max(desired_speed, min(float(args.base_speed) * 0.9, float(args.max_speed) * 0.55))
            else:
                speed_factor = min(obstacle_factor, heading_factor)
                desired_speed *= speed_factor
                desired_speed *= attitude_factor

            if front_blocked_persisted:
                # Avoid dead-stop lockups unless blockage is persistent and geometry is truly critical.
                if (geom_clearance_m > (hard_stop_dist + 0.45)) and (yaw_err_abs < 45.0):
                    crawl = min(float(args.min_crawl_speed), float(args.max_speed))
                    desired_speed = max(desired_speed, crawl)
                else:
                    desired_speed = 0.0

            speed_planar_now = math.hypot(dstate.vx, dstate.vy)
            attitude_unstable = (
                abs(dstate.roll) > float(args.max_roll_guard_deg)
                or abs(dstate.pitch) > float(args.max_pitch_guard_deg)
            )
            sideslip_unstable = (
                abs(sideslip_now_deg) > float(args.max_sideslip_guard_deg)
                and speed_planar_now >= float(args.sideslip_speed_guard_mps)
            )

            if attitude_unstable or sideslip_unstable:
                if unstable_since is None:
                    unstable_since = now
                elif (now - unstable_since) >= float(args.unstable_persist_sec):
                    recovery_until = max(recovery_until, now + float(args.recovery_hold_sec))
                    unstable_since = None
                    if (now - last_recovery_log) > 0.7:
                        log(
                            "Stability guard engaged | "
                            f"roll={dstate.roll:.1f} pitch={dstate.pitch:.1f} "
                            f"sideslip={sideslip_now_deg:.1f} speed={speed_planar_now:.2f}"
                        )
                        last_recovery_log = now
            else:
                unstable_since = None

            recovery_mode = now < recovery_until
            if recovery_mode:
                desired_speed = min(desired_speed, float(args.recovery_speed_mps))
                yaw_target = map_yaw_deg

            vx_des = nav_ux * desired_speed
            vy_des = nav_uy * desired_speed

            # Acceleration-limit + light low-pass to avoid twitch.
            dv = max_accel_world * max(dt, 1e-3)
            vx_cmd = max(prev_vx_cmd - dv, min(prev_vx_cmd + dv, vx_des))
            vy_cmd = max(prev_vy_cmd - dv, min(prev_vy_cmd + dv, vy_des))
            alpha = 0.25
            vx_cmd = (1 - alpha) * prev_vx_cmd + alpha * vx_cmd
            vy_cmd = (1 - alpha) * prev_vy_cmd + alpha * vy_cmd
            prev_vx_cmd, prev_vy_cmd = vx_cmd, vy_cmd

            target_yaw = yaw_target
            diff = shortest_diff(map_yaw_deg, target_yaw)

            # Limit yaw change per cycle to prevent violent spins.
            max_yaw_step = float(args.yaw_rate_limit) * max(dt, 1e-3)
            diff = max(-max_yaw_step, min(max_yaw_step, diff))
            cmd_map_yaw = wrap_deg(map_yaw_deg + diff)
            cmd_yaw = map_yaw_to_heading(cmd_map_yaw)
            if recovery_mode:
                cmd_map_yaw = map_yaw_deg
                cmd_yaw = dstate.yaw

            # Body-frame guidance: avoid backward flight, cap side-slip, then transform to NED.
            yaw_err_deg = shortest_diff(map_yaw_deg, target_yaw)
            yaw_err_rad = math.radians(yaw_err_deg)
            fwd_des = max(0.0, desired_speed * math.cos(yaw_err_rad))
            lat_gain = 0.08 if args.precision_mode else 0.35
            lat_des = lat_gain * desired_speed * math.sin(yaw_err_rad)
            if abs(yaw_err_deg) >= float(args.heading_align_stop_deg):
                fwd_des = min(fwd_des, float(args.heading_stop_forward_mps))
                lat_des = 0.0
            elif abs(yaw_err_deg) >= float(args.heading_align_slow_deg):
                fwd_des *= float(args.heading_slow_forward_scale)
                lat_des *= float(args.heading_slow_lateral_scale)
            if recovery_mode:
                fwd_des = min(fwd_des, float(args.recovery_speed_mps))
                lat_des = 0.0
            if args.precision_mode and abs(yaw_err_deg) > float(args.forward_hold_deg):
                fwd_des *= 0.70
                lat_des *= 0.15
            if front_eval_dist < (hard_stop_dist + 0.8):
                lat_des *= 0.2
            lat_limit_scale = args.max_lateral_ratio if args.precision_mode else 0.15
            lat_limit = lat_limit_scale * max(1.0, float(args.max_speed))
            lat_des = clamp(lat_des, -lat_limit, lat_limit)

            db = max_accel_body * max(dt, 1e-3)
            lat_acc_cmd = (lat_des - prev_lat_cmd) / max(dt, 1e-3)
            lat_acc_cmd = clamp(lat_acc_cmd, -float(args.max_lateral_accel_mps2), float(args.max_lateral_accel_mps2))
            tilt_target_deg = math.degrees(math.atan2(abs(lat_acc_cmd), 9.81))
            if tilt_target_deg > float(args.max_tilt_deg):
                tilt_scale = float(args.max_tilt_deg) / max(1e-6, tilt_target_deg)
                lat_des *= tilt_scale
                lat_acc_cmd *= tilt_scale
                tilt_target_deg = float(args.max_tilt_deg)

            fwd_cmd = clamp(fwd_des, prev_fwd_cmd - db, prev_fwd_cmd + db)
            lat_cmd = clamp(lat_des, prev_lat_cmd - db, prev_lat_cmd + db)
            prev_fwd_cmd, prev_lat_cmd = fwd_cmd, lat_cmd

            yaw_rad = math.radians(map_yaw_deg)
            c = math.cos(yaw_rad)
            s = math.sin(yaw_rad)
            vx_cmd_map = c * fwd_cmd - s * lat_cmd
            vy_cmd_map = s * fwd_cmd + c * lat_cmd

            vx_cmd, vy_cmd = map_xy_to_ned(vx_cmd_map, vy_cmd_map)

            prev_vx_cmd, prev_vy_cmd = vx_cmd, vy_cmd

            # Runtime flight-quality metrics.
            map_vx, map_vy = ned_to_map_xy(dstate.vx, dstate.vy)
            yaw_rad_metric = math.radians(map_yaw_deg)
            c_metric = math.cos(yaw_rad_metric)
            s_metric = math.sin(yaw_rad_metric)
            v_forward = (map_vx * c_metric) + (map_vy * s_metric)
            v_lateral = (-map_vx * s_metric) + (map_vy * c_metric)
            sideslip_deg = math.degrees(math.atan2(v_lateral, max(0.3, abs(v_forward))))
            heading_error_deg = shortest_diff(map_yaw_deg, yaw_target)
            last_heading_err_abs = abs(heading_error_deg)
            progress_mps = (dx / max(1e-6, dist)) * map_vx + (dy / max(1e-6, dist)) * map_vy

            # Deadlock escape: large persistent heading error + no progress means route/avoidance lock.
            heading_stall_eligible = (
                (now - goal_set_at) >= float(args.heading_stall_grace_sec)
                and (now - last_replan_at) >= float(args.replan_cooldown_sec)
            )

            if (
                heading_stall_eligible
                and
                abs(heading_error_deg) >= float(args.heading_stall_err_deg)
                and abs(progress_mps) <= float(args.heading_stall_progress_mps)
            ):
                heading_stall_strikes += 1
            else:
                heading_stall_strikes = 0

            if heading_stall_strikes >= int(args.heading_stall_strikes):
                log(
                    "Heading-stall detected -> force replan "
                    f"(head_err={heading_error_deg:.1f}deg, progress={progress_mps:.2f}mps, "
                    f"front={front_eval_dist:.2f}m, geom={geom_clearance_m:.2f}m)"
                )
                goal_x, goal_y = pick_new_goal()
                goal_set_at = time.time()
                last_replan_at = now
                current_path = []
                heading_stall_strikes = 0
                low_progress_strikes = 0
                continue

            if args.precision_mode and (time.time() - metrics_log_at) >= max(0.5, float(args.metrics_log_sec)):
                log(
                    "FALCON metrics | "
                    f"xtrack={cross_track_m:.2f}m "
                    f"head_err={heading_error_deg:.1f}deg "
                    f"sideslip={sideslip_deg:.1f}deg "
                    f"front_clear={front_eval_dist:.2f}m "
                    f"geom_clear={geom_clearance_m:.2f}m "
                    f"tilt={tilt_target_deg:.1f}deg "
                    f"progress={progress_mps:.2f}mps"
                )
                metrics_log_at = time.time()

            vz_cmd = 0.0
            if takeoff_target_alt is not None:
                if dstate.rel_alt < max(0.8, takeoff_target_alt - 0.4):
                    vx_cmd = 0.0
                    vy_cmd = 0.0
                    vz_cmd = -clamp(max(0.8, takeoff_target_alt - dstate.rel_alt), 0.8, 1.8)
                    cmd_yaw = dstate.yaw
                else:
                    log(f"Takeoff climb complete at {dstate.rel_alt:.2f}m (target {takeoff_target_alt:.2f}m)")
                    takeoff_target_alt = None

            if offboard_active:
                await drone.offboard.set_velocity_ned(
                    VelocityNedYaw(vx_cmd, vy_cmd, vz_cmd, cmd_yaw)
                )

            # ── Derived quantities for the enriched row ──────────────────────────────
            _gs    = math.sqrt(dstate.vx**2 + dstate.vy**2)
            _cog   = (math.degrees(math.atan2(dstate.vy, dstate.vx)) + 360) % 360
            _d2g   = math.sqrt((px - goal_x)**2 + (py - goal_y)**2)
            _mission_elapsed = (time.time() - airborne_since) if airborne_since else 0.0
            _alt_m = max(0.0, dstate.rel_alt)
            _temp  = isa_temperature(_alt_m)
            _rho   = isa_density(_alt_m)
            # effective airspeed = ground speed corrected by wind (simplified scalar)
            _wind_speed = wind_model.speed if wind_model is not None else 0.0
            _eas   = max(0.0, _gs - _wind_speed * 0.5)
            # obstacle count within slow_down_dist
            try:
                _obs_near = int(np.sum(sim_lidar < slow_down_dist))
            except Exception:
                _obs_near = 0
            # path waypoints remaining
            _wps_rem = len(waypoints) - wp_idx if 'waypoints' in dir() else 0
            # flight phase: 0=GROUND 1=TAKEOFF 2=CRUISE 3=APPROACH 4=HOVER 5=LAND
            if not dstate.in_air:
                _phase = 0
            elif dstate.rel_alt < (args.alt * 0.8):
                _phase = 1  # still climbing toward cruise
            elif _d2g < 4.0:
                _phase = 4  # hover near goal
            elif _d2g < 15.0:
                _phase = 3  # approach
            elif _gs < 0.3:
                _phase = 4  # stationary airborne
            else:
                _phase = 2  # cruise

            row = [
                # ── original 24 columns ──
                time.time(),
                dstate.lat,
                dstate.lon,
                dstate.rel_alt,
                dstate.vx,
                dstate.vy,
                dstate.vz,
                dstate.yaw,
                vx_cmd,
                vy_cmd,
                vz_cmd,
                cmd_yaw,
                min_dist,
                front_eval_dist,
                cross_track_m,
                heading_error_deg,
                sideslip_deg,
                progress_mps,
                geom_clearance_m,
                geom_threat,
                tilt_target_deg,
                json.dumps(sim_lidar.tolist()),
                goal_x,
                goal_y,
                # ── new 34 enriched columns ──
                round(dstate.roll,  4),
                round(dstate.pitch, 4),
                round(dstate.roll_rate_dps,  4),
                round(dstate.pitch_rate_dps, 4),
                round(dstate.yaw_rate_dps,   4),
                round(dstate.accel_x_ms2, 4),
                round(dstate.accel_y_ms2, 4),
                round(dstate.accel_z_ms2, 4),
                (round(dstate.battery_voltage_v, 3) if dstate.battery_voltage_v is not None else ""),
                (round(dstate.battery_current_a, 3) if dstate.battery_current_a is not None else ""),
                (round(dstate.battery_remaining_pct, 2) if dstate.battery_remaining_pct is not None else ""),
                (round(_batt_p, 2) if _batt_p is not None else ""),
                (round(battery_model.energy_consumed_wh, 4) if battery_model is not None else ""),
                (round(battery_model.flight_time_remaining(dstate.vx, dstate.vy, dstate.vz), 1) if battery_model is not None else ""),
                (round(wind_model.north, 4) if wind_model is not None else ""),
                (round(wind_model.east, 4) if wind_model is not None else ""),
                (round(wind_model.speed, 4) if wind_model is not None else ""),
                (round(wind_model.direction_deg, 2) if wind_model is not None else ""),
                round(_temp,  2),
                round(_rho,   5),
                round(_gs,    4),
                round(_cog,   2),
                round(_d2g,   3),
                _wps_rem,
                round(_mission_elapsed, 2),
                round(total_distance_m, 3),
                _phase,
                dstate.gps_fix_type,
                dstate.gps_num_sats,
                round(dstate.gps_hdop, 2),
                round(dstate.altitude_msl_m, 3),
                _obs_near,
                round(_eas, 4),
                int(_is_replanning),
                int(_is_recovering),
            ]

            # --- Redis Bridge Publish ---
            if redis_client:
                # 1. Publish Telemetry
                telemetry_data = {
                    "drone_id": args.drone_id,
                    "latitude": dstate.lat,
                    "longitude": dstate.lon,
                    "altitude": dstate.rel_alt,
                    "heading": dstate.yaw,
                    "speed": math.sqrt(dstate.vx**2 + dstate.vy**2),
                    "armed": dstate.armed,
                    "in_air": dstate.in_air,
                    "mode": dstate.mode or "TEACHER_BRIDGE",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                if dstate.battery_remaining_pct is not None:
                    telemetry_data["battery"] = round(float(dstate.battery_remaining_pct), 1)
                if wind_model is not None:
                    telemetry_data["environment"] = {
                        "wind_north_mps": float(wind_model.north),
                        "wind_east_mps": float(wind_model.east),
                        "wind_speed_mps": float(wind_model.speed),
                        "wind_dir_deg": float(wind_model.direction_deg),
                        "synthetic_environment": True,
                    }
                if external_mission and external_mission.get("status") in ("ACTIVE", "PAUSED"):
                    total_waypoints = len(external_mission.get("waypoints") or [])
                    current_idx = int(external_mission.get("current_idx") or 0)
                    telemetry_data.update({
                        "mission_type": external_mission.get("mission_type") or "CUSTOM",
                        "mission_status": external_mission.get("status"),
                        "total_waypoints": total_waypoints,
                        "current_waypoint_index": min(total_waypoints, current_idx + 1) if total_waypoints else 0,
                        "estimated_remaining_s": max(0, int((total_waypoints - current_idx) * 60)) if total_waypoints else 0,
                        "started_at": external_mission.get("started_at"),
                    })
                try:
                    await redis_client.publish('telemetry', json.dumps(telemetry_data))
                except Exception:
                    pass
                
                # 2. Check Commands  (drain all pending; break when queue is empty)
                try:
                    while True:
                        message = await redis_pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
                        if message is None:
                            break  # no more messages – exit drain loop so writer.writerow() is reached
                        if message['type'] != 'message':
                            continue
                        raw = message.get('data')
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode('utf-8', errors='replace')
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        if (payload.get('drone_id') or '').strip() not in ('', args.drone_id):
                            continue
                        if True:  # scoping block (was: outer `if message and ...`)
                            action = payload.get('action')
                            log(f"--> Received Command: {action}")

                            if action == 'arm':
                                try:
                                    await drone.action.arm()
                                except Exception as e:
                                    if 'COMMAND_DENIED' in str(e).upper():
                                        log("!! Arm denied, re-applying demo PX4 params and retrying once...")
                                        await apply_demo_px4_params(drone)
                                        await asyncio.sleep(0.25)
                                        try:
                                            await drone.action.arm()
                                        except Exception as retry_exc:
                                            log(f"!! Arm retry failed: {retry_exc}")
                                    else:
                                        log(f"!! Arm failed: {e}")

                            elif action == 'disarm':
                                try:
                                    takeoff_target_alt = None
                                    if dstate.in_air or dstate.rel_alt > 0.6:
                                        log("!! Disarm ignored: vehicle is airborne")
                                    else:
                                        try:
                                            await drone.offboard.stop()
                                        except Exception:
                                            pass
                                        offboard_active = False
                                        await drone.action.disarm()
                                except Exception as e:
                                    log(f"!! Disarm failed: {e}")

                            elif action == 'takeoff':
                                try:
                                    target_alt = float((payload.get('params') or {}).get('altitude', args.alt))
                                    target_alt = max(1.5, target_alt)
                                    if not dstate.armed:
                                        await drone.action.arm()
                                        await asyncio.sleep(1.5)
                                    else:
                                        await asyncio.sleep(0.8)
                                    if (not args.bridge_only) and offboard_active:
                                        try:
                                            await drone.offboard.stop()
                                        except Exception:
                                            pass
                                        offboard_active = False
                                        await asyncio.sleep(0.2)
                                    try:
                                        await drone.action.set_takeoff_altitude(target_alt)
                                    except Exception:
                                        pass
                                    await drone.action.takeoff()
                                    await asyncio.sleep(1.0)
                                    if (not args.bridge_only) and (not offboard_active):
                                        try:
                                            await ensure_offboard_started()
                                        except Exception as offboard_exc:
                                            log(f"!! Offboard start warning after takeoff: {offboard_exc}")
                                    takeoff_target_alt = None if args.bridge_only else target_alt
                                    log(f"--> Takeoff override armed to {target_alt:.1f}m")
                                except Exception as e:
                                    if 'COMMAND_DENIED' in str(e).upper():
                                        log("!! Takeoff denied, re-applying demo PX4 params and retrying once...")
                                        await apply_demo_px4_params(drone)
                                        await asyncio.sleep(0.25)
                                        try:
                                            if not dstate.armed:
                                                await drone.action.arm()
                                                await asyncio.sleep(1.5)
                                            else:
                                                await asyncio.sleep(0.8)
                                            if (not args.bridge_only) and offboard_active:
                                                try:
                                                    await drone.offboard.stop()
                                                except Exception:
                                                    pass
                                                offboard_active = False
                                                await asyncio.sleep(0.2)
                                            try:
                                                await drone.action.set_takeoff_altitude(target_alt)
                                            except Exception:
                                                pass
                                            await drone.action.takeoff()
                                            await asyncio.sleep(1.0)
                                            if (not args.bridge_only) and (not offboard_active):
                                                try:
                                                    await ensure_offboard_started()
                                                except Exception as offboard_exc:
                                                    log(f"!! Offboard start warning after takeoff retry: {offboard_exc}")
                                            takeoff_target_alt = None if args.bridge_only else target_alt
                                            log(f"--> Takeoff retry armed to {target_alt:.1f}m")
                                        except Exception as retry_exc:
                                            log(f"!! Takeoff retry failed: {retry_exc}")
                                    else:
                                        log(f"!! Takeoff failed: {e}")

                            elif action == 'land':
                                try:
                                    takeoff_target_alt = None
                                    try:
                                        await drone.offboard.stop()
                                    except Exception:
                                        pass
                                    offboard_active = False
                                    await drone.action.land()
                                except Exception as e:
                                    log(f"!! Land failed: {e}")

                            elif action == 'goto':
                                target_lat = float(payload['params']['latitude'])
                                target_lon = float(payload['params']['longitude'])
                                if not offboard_active:
                                    await ensure_offboard_started()
                                external_mission = None
                                set_goal_from_global(target_lat, target_lon)
                                log(f"--> Override Goal: {goal_x:.1f}, {goal_y:.1f}")

                            elif action == 'mission_start':
                                params = payload.get('params') or {}
                                raw_waypoints = params.get('waypoints') or []
                                mission_type = str(params.get('mission_type') or 'CUSTOM')
                                parsed_waypoints = []
                                for wp in raw_waypoints:
                                    if isinstance(wp, (list, tuple)) and len(wp) >= 2:
                                        parsed_waypoints.append([
                                            float(wp[0]),
                                            float(wp[1]),
                                            float(wp[2]) if len(wp) > 2 else float(args.alt),
                                        ])
                                if not parsed_waypoints:
                                    log("!! Mission start ignored: no valid waypoints")
                                    continue
                                external_mission = {
                                    "mission_type": mission_type,
                                    "waypoints": parsed_waypoints,
                                    "current_idx": 0,
                                    "status": "ACTIVE",
                                    "started_at": datetime.now(timezone.utc).isoformat(),
                                    "await_takeoff_alt": None,
                                }
                                target_alt = max(1.5, float(parsed_waypoints[0][2]))
                                if not dstate.in_air and dstate.rel_alt < max(0.8, target_alt - 0.7):
                                    takeoff_ok = await trigger_takeoff_best_effort(target_alt, "Mission")
                                    if takeoff_ok:
                                        external_mission["await_takeoff_alt"] = target_alt
                                        log(f"--> External mission armed; awaiting climb to {target_alt:.1f}m")
                                    else:
                                        external_mission["status"] = "FAILED"
                                        log("!! External mission aborted: takeoff could not be initiated")
                                else:
                                    if not offboard_active:
                                        await ensure_offboard_started()
                                    set_goal_from_global(float(parsed_waypoints[0][0]), float(parsed_waypoints[0][1]))
                                    log(f"--> External mission started with {len(parsed_waypoints)} waypoint(s)")

                            elif action == 'mission_pause':
                                if external_mission and external_mission.get("status") == "ACTIVE":
                                    external_mission["status"] = "PAUSED"
                                    px_hold, py_hold = get_local_pos()
                                    goal_x, goal_y = px_hold, py_hold
                                    goal_set_at = time.time()
                                    current_path = [(px_hold, py_hold)]
                                    path_index = 0
                                    log("--> External mission paused")

                            elif action == 'mission_resume':
                                if external_mission and external_mission.get("status") == "PAUSED":
                                    external_mission["status"] = "ACTIVE"
                                    if external_mission.get("await_takeoff_alt") is None:
                                        wp = external_mission["waypoints"][external_mission["current_idx"]]
                                        if not offboard_active:
                                            await ensure_offboard_started()
                                        set_goal_from_global(float(wp[0]), float(wp[1]))
                                    log("--> External mission resumed")

                            elif action == 'mission_stop':
                                stop_external_mission("--> External mission stopped")
                                
                except Exception as e:
                    log(f"!! Redis command loop warning: {e}")

            writer.writerow(row)
            f.flush()  # guarantee data lands on disk each cycle

            # --- Segmentation feed (lidar-derived obstacle detection for app Analytics panel) ---
            if dstate.in_air:
                _threat = float(geom_threat)
                _front_conf = max(0.0, min(1.0, 1.0 - (float(front_eval_dist) / 20.0)))
                if _threat > 0.15 or _front_conf > 0.3:
                    _det_class = "obstacle" if (_threat > 0.35 or _front_conf > 0.55) else "proximity_alert"
                    _max_conf = round(max(_threat, _front_conf), 3)
                    seg_log_writer.writerow([
                        args.drone_id,
                        _det_class,
                        _max_conf,
                        datetime.now(timezone.utc).isoformat(),
                    ])
                    seg_log_f.flush()
    finally:
        try:
            try:
                await drone.offboard.stop()
            except Exception:
                pass
            await drone.action.land()
        except Exception:
            pass
        f.close()
        try:
            seg_log_f.close()
        except Exception:
            pass
        if args.auto_analyze:
            out_path = Path(args.out)
            stem = out_path.stem
            report_path = args.analysis_report if args.analysis_report else str(out_path.with_name(f"{stem}_analysis.json"))
            analyze_telemetry_csv(args.out, report_path)
        print("Done (ONLINE mode)!")


# --- MAIN (OFFLINE) ---
def collect_data_offline(args):
    world_map = Map(args.sdf_path)
    grid = GridMap(world_map.obstacles, resolution=1.0, margin=2.5)

    f = open(args.out, "w", newline="", encoding="utf-8")
    writer = csv.writer(f)
    header = [
        "timestamp",
        "lat",
        "lon",
        "rel_alt",
        "vx",
        "vy",
        "vz",
        "yaw",
        "cmd_vx",
        "cmd_vy",
        "cmd_vz",
        "cmd_yaw",
        "lidar_min",
        "lidar_json",
        "goal_x",
        "goal_y",
    ]
    writer.writerow(header)

    px, py = 0.0, 0.0
    yaw = 0.0
    alt = args.alt
    vx = vy = vz = 0.0

    start_time = time.time()
    last_step = time.time()

    current_path = []
    path_index = 0
    goal_x, goal_y = 0.0, 0.0

    def pick_new_goal_offline(cx, cy):
        while True:
            gx = np.random.randint(10, grid.width - 10)
            gy = np.random.randint(10, grid.height - 10)
            if not grid.is_blocked(gx, gy):
                wx, wy = grid.grid_to_world(gx, gy)
                dist = math.sqrt((wx - cx) ** 2 + (wy - cy) ** 2)
                if dist > 30:
                    return wx, wy

    goal_x, goal_y = pick_new_goal_offline(px, py)
    print(f"[OFFLINE] First Goal: {goal_x:.1f}, {goal_y:.1f}")

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > args.duration:
                break

            now = time.time()
            dt = now - last_step
            if dt < 0.1:
                time.sleep(0.01)
                continue
            last_step = now

            if not current_path or path_index >= len(current_path):
                print(f"[OFFLINE] Planning A* to {goal_x:.0f},{goal_y:.0f}...")
                path = astar(grid, (px, py), (goal_x, goal_y))
                if not path:
                    print("[OFFLINE] Path failed! Picking new goal.")
                    goal_x, goal_y = pick_new_goal_offline(px, py)
                    continue

                current_path = path[::2] + [path[-1]]
                path_index = 0
                print(f"[OFFLINE] Path found! {len(current_path)} waypoints")

            lookahead_dist = 4.0
            target_pt = current_path[path_index]

            for i in range(path_index, len(current_path)):
                pt = current_path[i]
                d = math.sqrt((pt[0] - px) ** 2 + (pt[1] - py) ** 2)
                if d > lookahead_dist:
                    target_pt = pt
                    path_index = i
                    break

                if i == len(current_path) - 1 and d < 2.0:
                    print("[OFFLINE] Goal Reached! New Goal...")
                    goal_x, goal_y = pick_new_goal_offline(px, py)
                    current_path = []
                    break

            if not current_path:
                continue

            tx, ty = target_pt
            dx = tx - px
            dy = ty - py
            dist = math.sqrt(dx * dx + dy * dy)

            desired_speed = args.max_speed
            cmd_vx = (dx / dist) * desired_speed if dist > 0 else 0.0
            cmd_vy = (dy / dist) * desired_speed if dist > 0 else 0.0

            target_yaw = math.degrees(math.atan2(dy, dx))
            yaw_err = shortest_diff(yaw, target_yaw)
            cmd_yaw_rate = max(-45.0, min(45.0, yaw_err * 2.0))

            yaw = wrap_deg(yaw + cmd_yaw_rate * dt)
            px += cmd_vx * dt
            py += cmd_vy * dt
            vx = cmd_vx
            vy = cmd_vy
            vz = 0.0

            sim_lidar = world_map.simulate_lidar(px, py, alt, yaw)
            min_dist = float(np.min(sim_lidar))

            row = [
                time.time(),
                0.0,
                0.0,
                alt,
                vx,
                vy,
                vz,
                yaw,
                cmd_vx,
                cmd_vy,
                0.0,
                cmd_yaw_rate,
                min_dist,
                json.dumps(sim_lidar.tolist()),
                goal_x,
                goal_y,
            ]
            writer.writerow(row)
    finally:
        f.close()
        if args.auto_analyze:
            out_path = Path(args.out)
            stem = out_path.stem
            report_path = args.analysis_report if args.analysis_report else str(out_path.with_name(f"{stem}_analysis.json"))
            analyze_telemetry_csv(args.out, report_path)
        print("Done (OFFLINE mode)!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drone-id", type=str, default=os.environ.get("DRONE_ID", "SENTINEL-01"))
    parser.add_argument(
        "--no_lock",
        action="store_true",
        help="Disable the single-instance lock (advanced/debug). Default lock is per --drone-id.",
    )
    data_root = (os.environ.get("LESNAR_DATA_ROOT") or "dataset").strip() or "dataset"
    default_out = str(Path(data_root) / "px4_teacher" / "telemetry_god.csv")
    parser.add_argument("--out", type=str, default=default_out)
    parser.add_argument("--system", type=str, default="udpin://0.0.0.0:14540")
    parser.add_argument("--duration", type=float, default=0.0, help="Run duration in seconds. Use 0 for continuous run.")
    parser.add_argument("--bridge_only", action="store_true", help="Run as a passive control bridge for the app without autonomous teacher navigation.")
    parser.add_argument("--no_bridge_only", action="store_false", dest="bridge_only", help="Enable autonomous teacher navigation/pathfinding.")
    parser.add_argument("--alt", type=float, default=15.0)
    parser.add_argument("--hz", type=float, default=20.0)
    parser.add_argument("--base_speed", type=float, default=2.2)
    parser.add_argument("--max_speed", type=float, default=4.2)
    parser.add_argument("--min_crawl_speed", type=float, default=0.6, help="Minimum forward crawl speed used near hard-stop threshold when corridor is still feasible.")
    parser.add_argument("--yaw_rate_limit", type=float, default=65.0)
    parser.add_argument("--safe_presentation_profile", action="store_true", help="Enable conservative safety limits suitable for demos.")
    parser.add_argument("--no_safe_presentation_profile", action="store_false", dest="safe_presentation_profile", help="Disable conservative demo safety profile.")
    parser.set_defaults(safe_presentation_profile=True)
    parser.add_argument("--precision_mode", action="store_true", help="Enable strict path-tracking Falcon mode.")
    parser.add_argument("--disable_wind_model", action="store_true", help="Disable wind/environment model (wind is enabled by default).")
    parser.add_argument("--enable_battery_model", action="store_true", help="Enable battery/power model fields in CSV (OFF by default; does not override MAVSDK battery telemetry).")
    parser.add_argument("--enable_synthetic_models", action="store_true", help="Legacy alias: enable both wind model and battery model fields.")
    parser.add_argument("--no_precision_mode", action="store_false", dest="precision_mode", help="Disable Falcon precision controller.")
    parser.set_defaults(precision_mode=True)
    parser.add_argument("--obstacle_sector_deg", type=float, default=14.0, help="Front obstacle sector width in degrees.")
    parser.add_argument("--crosstrack_kp", type=float, default=3.0, help="Cross-track to heading correction gain (deg per meter).")
    parser.add_argument("--crosstrack_heading_cap_deg", type=float, default=14.0, help="Max cross-track heading correction in degrees.")
    parser.add_argument("--max_lateral_ratio", type=float, default=0.04, help="Max lateral speed as ratio of max_speed in precision mode.")
    parser.add_argument("--forward_hold_deg", type=float, default=45.0, help="Hold forward speed down when heading error exceeds this.")
    parser.add_argument("--heading_align_slow_deg", type=float, default=22.0, help="Begin strongly damping translation when heading error exceeds this.")
    parser.add_argument("--heading_align_stop_deg", type=float, default=38.0, help="Nearly stop translation and yaw in place when heading error exceeds this.")
    parser.add_argument("--heading_slow_min_ratio", type=float, default=0.22, help="Minimum speed ratio while in heading-alignment slow zone.")
    parser.add_argument("--heading_stop_speed_ratio", type=float, default=0.10, help="Maximum speed ratio when heading error exceeds the stop threshold.")
    parser.add_argument("--heading_stop_forward_mps", type=float, default=0.18, help="Maximum forward speed when yaw error is above the heading stop threshold.")
    parser.add_argument("--heading_slow_forward_scale", type=float, default=0.45, help="Forward speed multiplier in the heading-alignment slow zone.")
    parser.add_argument("--heading_slow_lateral_scale", type=float, default=0.08, help="Lateral speed multiplier in the heading-alignment slow zone.")
    parser.add_argument("--obstacle_lookahead_m", type=float, default=14.0, help="Geometry obstacle lookahead distance in meters.")
    parser.add_argument("--obstacle_corridor_deg", type=float, default=65.0, help="Forward corridor half-angle for geometry avoidance.")
    parser.add_argument("--obstacle_safety_margin_m", type=float, default=2.0, help="Extra obstacle volume margin in meters.")
    parser.add_argument("--obstacle_height_clearance_m", type=float, default=1.2, help="Ignore obstacles lower than altitude minus this clearance.")
    parser.add_argument("--avoidance_gain", type=float, default=1.2, help="Gain for geometry threat to route/avoidance blending.")
    parser.add_argument("--max_avoidance_blend", type=float, default=0.85, help="Upper bound on avoidance blending factor (ceiling ignored at threat >= 0.9).")
    parser.add_argument("--max_lateral_accel_mps2", type=float, default=2.0, help="Max lateral acceleration command magnitude.")
    parser.add_argument("--max_tilt_deg", type=float, default=12.0, help="Maximum target lateral tilt angle for smooth maneuvering.")
    parser.add_argument("--max_roll_guard_deg", type=float, default=30.0, help="Trigger recovery if absolute roll exceeds this (deg).")
    parser.add_argument("--max_pitch_guard_deg", type=float, default=30.0, help="Trigger recovery if absolute pitch exceeds this (deg).")
    parser.add_argument("--attitude_soft_guard_ratio", type=float, default=0.55, help="Begin damping translation once roll/pitch reaches this fraction of the hard guard.")
    parser.add_argument("--attitude_soft_min_speed_ratio", type=float, default=0.18, help="Minimum speed ratio allowed once soft attitude damping is active.")
    parser.add_argument("--max_sideslip_guard_deg", type=float, default=28.0, help="Trigger recovery if absolute sideslip exceeds this (deg).")
    parser.add_argument("--sideslip_speed_guard_mps", type=float, default=1.2, help="Minimum horizontal speed before sideslip guard can trigger.")
    parser.add_argument("--unstable_persist_sec", type=float, default=0.35, help="Seconds instability must persist before recovery mode engages.")
    parser.add_argument("--recovery_hold_sec", type=float, default=1.8, help="Seconds to hold conservative recovery commands once triggered.")
    parser.add_argument("--recovery_speed_mps", type=float, default=0.8, help="Max forward speed while recovery mode is active.")
    parser.add_argument("--front_filter_alpha", type=float, default=0.72, help="EMA smoothing factor for front clearance (higher=more smoothing).")
    parser.add_argument("--front_block_debounce_sec", type=float, default=0.7, help="Seconds front blockage must persist before hard-stop logic engages.")
    parser.add_argument("--front_recover_margin_m", type=float, default=0.55, help="Hysteresis margin above hard-stop distance to clear blocked state.")
    parser.add_argument("--front_zero_glitch_threshold_m", type=float, default=0.05, help="Treat front distances below this as potential glitch candidates.")
    parser.add_argument("--front_zero_ignore_geom_clear_m", type=float, default=4.0, help="Ignore zero-front spikes when geometry clearance is above this.")
    parser.add_argument("--front_zero_ignore_geom_threat", type=float, default=0.2, help="Ignore zero-front spikes when geometry threat is below this.")
    parser.add_argument("--metrics_log_sec", type=float, default=1.5, help="Seconds between Falcon quality metric logs.")
    parser.add_argument("--heading_stall_err_deg", type=float, default=110.0, help="Heading error threshold for stall detection.")
    parser.add_argument("--heading_stall_progress_mps", type=float, default=0.20, help="Progress threshold below which heading-stall samples count.")
    parser.add_argument("--heading_stall_strikes", type=int, default=12, help="Consecutive heading-stall samples before forced replan.")
    parser.add_argument("--progress_window_sec", type=float, default=10.0, help="Seconds between anti-stall progress checks.")
    parser.add_argument("--min_progress_m", type=float, default=1.5, help="Minimum movement in progress window before counting a low-progress strike.")
    parser.add_argument("--replan_strikes", type=int, default=5, help="Consecutive low-progress strikes required before forcing a replan.")
    parser.add_argument("--goal_grace_sec", type=float, default=9.0, help="Grace period after setting a new goal before low-progress strikes can accumulate.")
    parser.add_argument("--replan_heading_hold_deg", type=float, default=80.0, help="Do not count low-progress strikes while heading error exceeds this angle.")
    parser.add_argument("--replan_cooldown_sec", type=float, default=3.5, help="Minimum seconds between forced replans to avoid oscillation.")
    parser.add_argument("--heading_stall_grace_sec", type=float, default=2.5, help="Ignore heading-stall counting briefly after each new goal/replan.")
    parser.add_argument("--sdf_path", type=str, default=os.environ.get("SDF_PATH", "obstacles.sdf"))
    parser.add_argument("--offline", action="store_true", help="Run without PX4/Gazebo (pure Python)")
    parser.add_argument(
        "--mavsdk-server",
        type=str,
        default=os.environ.get("MAVSDK_SERVER", "auto"),
        help="MAVSDK server host. Use 'auto' to let mavsdk-python spawn/manage it.",
    )
    parser.add_argument(
        "--mavsdk-port",
        type=int,
        default=int(os.environ.get("MAVSDK_PORT", 50051)),
        help="MAVSDK server port (ignored when --mavsdk-server auto).",
    )
    parser.add_argument("--redis-host", type=str, default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--auto_analyze", action="store_true", help="Automatically analyze telemetry CSV at end of run.")
    parser.add_argument("--no_auto_analyze", action="store_false", dest="auto_analyze", help="Disable end-of-run telemetry analysis.")
    parser.add_argument("--analysis_report", type=str, default="", help="Optional explicit path for JSON auto-analysis report.")
    parser.set_defaults(auto_analyze=True)
    parser.set_defaults(bridge_only=False)

    args = parser.parse_args()
    if args.safe_presentation_profile:
        args.hz = min(float(args.hz), 15.0)
        args.base_speed = min(float(args.base_speed), 0.9)
        args.max_speed = min(float(args.max_speed), 1.8)
        args.min_crawl_speed = min(float(args.min_crawl_speed), 0.22)
        args.yaw_rate_limit = min(float(args.yaw_rate_limit), 24.0)
        args.crosstrack_kp = min(float(args.crosstrack_kp), 2.0)
        args.crosstrack_heading_cap_deg = min(float(args.crosstrack_heading_cap_deg), 8.0)
        args.max_lateral_ratio = min(float(args.max_lateral_ratio), 0.015)
        args.avoidance_gain = min(float(args.avoidance_gain), 0.55)
        args.max_avoidance_blend = min(float(args.max_avoidance_blend), 0.32)
        args.max_lateral_accel_mps2 = min(float(args.max_lateral_accel_mps2), 0.55)
        args.max_tilt_deg = min(float(args.max_tilt_deg), 5.5)
        args.recovery_speed_mps = min(float(args.recovery_speed_mps), 0.35)
        args.heading_align_slow_deg = min(float(args.heading_align_slow_deg), 18.0)
        args.heading_align_stop_deg = min(float(args.heading_align_stop_deg), 30.0)
        args.heading_slow_min_ratio = min(float(args.heading_slow_min_ratio), 0.18)
        args.heading_stop_speed_ratio = min(float(args.heading_stop_speed_ratio), 0.06)
        args.heading_stop_forward_mps = min(float(args.heading_stop_forward_mps), 0.10)
        args.heading_slow_forward_scale = min(float(args.heading_slow_forward_scale), 0.30)
        args.heading_slow_lateral_scale = min(float(args.heading_slow_lateral_scale), 0.04)
        args.attitude_soft_guard_ratio = min(float(args.attitude_soft_guard_ratio), 0.45)
        args.attitude_soft_min_speed_ratio = min(float(args.attitude_soft_min_speed_ratio), 0.12)

    if args.offline:
        collect_data_offline(args)
    else:
        if not args.no_lock:
            acquire_single_instance_lock(args.drone_id)
        asyncio.run(collect_data(args))


