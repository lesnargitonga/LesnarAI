import asyncio
import argparse
import csv
import json
import math
import os
import time
import heapq
from collections import deque
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
        lookahead_m=12.0,
        corridor_deg=65.0,
        safety_margin_m=1.4,
        vertical_clearance_m=1.2,
    ):
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

            threat_dist = clamp((lookahead_m - clearance) / max(1e-6, lookahead_m), 0.0, 1.0)
            heading_weight = clamp(math.cos(math.radians(rel_bearing)), 0.0, 1.0)
            size_weight = clamp(obs.horizontal_size_m() / 4.0, 0.5, 2.0)
            threat = threat_dist * heading_weight * size_weight

            repel_x += threat * dir_away_x
            repel_y += threat * dir_away_y
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


# --- MAIN (ONLINE) ---
async def collect_data(args):
    """ONLINE MODE: PX4 + Gazebo + MAVSDK."""

    if System is None:
        raise RuntimeError("MAVSDK not available in this environment. Use --offline.")

    log("--> Starting teacher (ONLINE)...")
    world_map = Map(args.sdf_path)
    log("--> Map loaded.")
    grid = GridMap(world_map.obstacles, resolution=1.0, margin=1.5)
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

    dstate = DroneState()
    asyncio.create_task(telemetry_listener(drone, dstate))
    asyncio.create_task(local_pos_listener(drone, dstate))
    asyncio.create_task(att_listener(drone, dstate))

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

    print("--> Starting A* Pathfinding (ONLINE)...")
    try:
        # PX4 offboard best practice: stream setpoints before starting offboard.
        warmup_hz = max(5.0, float(args.hz))
        warmup_count = int(warmup_hz * 1.0)
        for _ in range(warmup_count):
            await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, dstate.yaw))
            await asyncio.sleep(1.0 / warmup_hz)
        await drone.offboard.start()
    except OffboardError as e:
        print(e)
        return

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
    ]
    writer.writerow(header)

    start_time = time.time()
    last_step = time.time()

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
    recent_goals = deque(maxlen=5)

    # Anti-loiter watchdog
    last_progress_check = time.time()
    progress_anchor = (0.0, 0.0)

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

    goal_x, goal_y = pick_new_goal()
    progress_anchor = get_local_pos()
    print(f"First Goal: {goal_x:.1f}, {goal_y:.1f}")

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > args.duration:
                break

            now = time.time()
            dt = now - last_step
            period = 1.0 / max(1.0, float(args.hz))
            if dt < period:
                await asyncio.sleep(max(0.0, period - dt))
                continue
            last_step = now

            px, py = get_local_pos()

            # If not making meaningful progress, force a replan/new mission goal.
            if now - last_progress_check > 8.0:
                moved = math.sqrt((px - progress_anchor[0]) ** 2 + (py - progress_anchor[1]) ** 2)
                if moved < 4.0:
                    print("Low progress detected -> replanning with a new goal")
                    goal_x, goal_y = pick_new_goal()
                    current_path = []
                progress_anchor = (px, py)
                last_progress_check = now

            if not current_path or path_index >= len(current_path):
                print(f"Planning A* to {goal_x:.0f},{goal_y:.0f}...")
                path = astar(grid, (px, py), (goal_x, goal_y))
                if not path:
                    print("Path failed! Picking new goal.")
                    goal_x, goal_y = pick_new_goal()
                    continue

                # Downsample less aggressively for smoother guidance.
                stride = 2 if args.precision_mode else 3
                current_path = path[::stride] + [path[-1]]
                path_index = 0
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
                    print("Goal Reached! New Goal...")
                    goal_x, goal_y = pick_new_goal()
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

            num_rays = len(sim_lidar)
            front_center = num_rays // 2
            front_half_window = max(2, int(round(num_rays * max(5.0, float(args.obstacle_sector_deg / 2.0)) / 360.0)))
            front_slice = sim_lidar[
                max(0, front_center - front_half_window) : min(num_rays, front_center + front_half_window + 1)
            ]
            front_min_dist = float(np.min(front_slice)) if len(front_slice) else min_dist

            avoid_x, avoid_y, geom_clearance_m, geom_threat = world_map.obstacle_avoidance_field(
                px,
                py,
                dstate.rel_alt,
                map_yaw_deg,
                lookahead_m=float(args.obstacle_lookahead_m),
                corridor_deg=float(args.obstacle_corridor_deg),
                safety_margin_m=float(args.obstacle_safety_margin_m),
                vertical_clearance_m=float(args.obstacle_height_clearance_m),
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
            if front_min_dist >= slow_down_dist:
                obstacle_factor = 1.0
            else:
                obstacle_factor = clamp(
                    (front_min_dist - hard_stop_dist) / max(1e-6, (slow_down_dist - hard_stop_dist)),
                    0.0,
                    1.0,
                )
            yaw_target_nom = math.degrees(math.atan2(nav_uy, nav_ux)) if (abs(nav_ux) + abs(nav_uy)) > 1e-6 else math.degrees(math.atan2(dy, dx))
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
            if args.precision_mode:
                desired_speed *= heading_factor
                if obstacle_factor < 1.0:
                    desired_speed *= obstacle_factor
                if geom_clearance_m < (hard_stop_dist + 1.4):
                    desired_speed *= clamp((geom_clearance_m - hard_stop_dist) / 1.4, 0.2, 1.0)
                if front_min_dist > (hard_stop_dist + 0.7):
                    desired_speed = max(desired_speed, min(float(args.base_speed) * 0.9, float(args.max_speed) * 0.55))
            else:
                speed_factor = min(obstacle_factor, heading_factor)
                desired_speed *= speed_factor

            if front_min_dist < hard_stop_dist:
                desired_speed = 0.0

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

            # Body-frame guidance: avoid backward flight, cap side-slip, then transform to NED.
            yaw_err_deg = shortest_diff(map_yaw_deg, target_yaw)
            yaw_err_rad = math.radians(yaw_err_deg)
            fwd_des = max(0.0, desired_speed * math.cos(yaw_err_rad))
            lat_gain = 0.08 if args.precision_mode else 0.35
            lat_des = lat_gain * desired_speed * math.sin(yaw_err_rad)
            if args.precision_mode and abs(yaw_err_deg) > float(args.forward_hold_deg):
                fwd_des *= 0.70
                lat_des *= 0.15
            if front_min_dist < (hard_stop_dist + 0.8):
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
            progress_mps = (dx / max(1e-6, dist)) * map_vx + (dy / max(1e-6, dist)) * map_vy

            if args.precision_mode and (time.time() - metrics_log_at) >= max(0.5, float(args.metrics_log_sec)):
                log(
                    "FALCON metrics | "
                    f"xtrack={cross_track_m:.2f}m "
                    f"head_err={heading_error_deg:.1f}deg "
                    f"sideslip={sideslip_deg:.1f}deg "
                    f"front_clear={front_min_dist:.2f}m "
                    f"geom_clear={geom_clearance_m:.2f}m "
                    f"tilt={tilt_target_deg:.1f}deg "
                    f"progress={progress_mps:.2f}mps"
                )
                metrics_log_at = time.time()

            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(vx_cmd, vy_cmd, 0.0, cmd_yaw)
            )

            row = [
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
                0.0,
                cmd_yaw,
                min_dist,
                front_min_dist,
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
                    "battery": 99.0,
                    "armed": True,
                    "mode": "TEACHER_BRIDGE",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                try:
                    await redis_client.publish('telemetry', json.dumps(telemetry_data))
                except Exception:
                    pass
                
                # 2. Check Commands
                try:
                    while True:
                        message = await redis_pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
                        if message and message['type'] == 'message':
                            raw = message.get('data')
                            if isinstance(raw, (bytes, bytearray)):
                                raw = raw.decode('utf-8', errors='replace')
                            payload = json.loads(raw)
                            if (payload.get('drone_id') or '').strip() not in ('', args.drone_id):
                                continue
                            
                            action = payload.get('action')
                            log(f"--> Received Command: {action}")
                            
                            if action == 'takeoff':
                                try:
                                    await drone.action.arm()
                                    await drone.action.takeoff()
                                except Exception as e:
                                    log(f"!! Takeoff failed: {e}")

                            elif action == 'land':
                                try:
                                    await drone.action.land()
                                    # Break the loop if landing? Optional.
                                except Exception as e:
                                    log(f"!! Land failed: {e}")

                            elif action == 'goto':
                                # Global (Lat/Lon) -> Local (North/East) relative to current
                                # Simple approximation for small localized missions
                                target_lat = float(payload['params']['latitude'])
                                target_lon = float(payload['params']['longitude'])
                                
                                # Current
                                lat0, lon0 = dstate.lat, dstate.lon
                                px0, py0 = get_local_pos()
                                
                                # Delta in NED-like meters
                                dLat = target_lat - lat0
                                dLon = target_lon - lon0
                                d_north = dLat * 111319.0
                                d_east = dLon * 111319.0 * math.cos(math.radians(lat0))

                                cur_map_x, cur_map_y = get_local_pos()
                                d_map_x, d_map_y = ned_to_map_xy(d_north, d_east)
                                new_x = cur_map_x + d_map_x
                                new_y = cur_map_y + d_map_y
                                
                                log(f"--> Override Goal: {new_x:.1f}, {new_y:.1f}")
                                goal_x, goal_y = new_x, new_y
                                current_path = [] # Trigger replan
                                
                except Exception as e:
                    pass

            writer.writerow(row)
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
        print("Done (ONLINE mode)!")


# --- MAIN (OFFLINE) ---
def collect_data_offline(args):
    world_map = Map(args.sdf_path)
    grid = GridMap(world_map.obstacles, resolution=1.0, margin=1.5)

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
        print("Done (OFFLINE mode)!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drone-id", type=str, default=os.environ.get("DRONE_ID", "SENTINEL-01"))
    parser.add_argument("--out", type=str, default="dataset/px4_teacher/telemetry_god.csv")
    parser.add_argument("--system", type=str, default="udpin://0.0.0.0:14540")
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--alt", type=float, default=15.0)
    parser.add_argument("--hz", type=float, default=20.0)
    parser.add_argument("--base_speed", type=float, default=6.0)
    parser.add_argument("--max_speed", type=float, default=12.0)
    parser.add_argument("--yaw_rate_limit", type=float, default=65.0)
    parser.add_argument("--precision_mode", action="store_true", help="Enable strict path-tracking Falcon mode.")
    parser.add_argument("--no_precision_mode", action="store_false", dest="precision_mode", help="Disable Falcon precision controller.")
    parser.set_defaults(precision_mode=True)
    parser.add_argument("--obstacle_sector_deg", type=float, default=14.0, help="Front obstacle sector width in degrees.")
    parser.add_argument("--crosstrack_kp", type=float, default=3.0, help="Cross-track to heading correction gain (deg per meter).")
    parser.add_argument("--crosstrack_heading_cap_deg", type=float, default=14.0, help="Max cross-track heading correction in degrees.")
    parser.add_argument("--max_lateral_ratio", type=float, default=0.04, help="Max lateral speed as ratio of max_speed in precision mode.")
    parser.add_argument("--forward_hold_deg", type=float, default=45.0, help="Hold forward speed down when heading error exceeds this.")
    parser.add_argument("--obstacle_lookahead_m", type=float, default=12.0, help="Geometry obstacle lookahead distance in meters.")
    parser.add_argument("--obstacle_corridor_deg", type=float, default=65.0, help="Forward corridor half-angle for geometry avoidance.")
    parser.add_argument("--obstacle_safety_margin_m", type=float, default=1.4, help="Extra obstacle volume margin in meters.")
    parser.add_argument("--obstacle_height_clearance_m", type=float, default=1.2, help="Ignore obstacles lower than altitude minus this clearance.")
    parser.add_argument("--avoidance_gain", type=float, default=0.95, help="Gain for geometry threat to route/avoidance blending.")
    parser.add_argument("--max_avoidance_blend", type=float, default=0.70, help="Upper bound on avoidance blending factor.")
    parser.add_argument("--max_lateral_accel_mps2", type=float, default=2.4, help="Max lateral acceleration command magnitude.")
    parser.add_argument("--max_tilt_deg", type=float, default=14.0, help="Maximum target lateral tilt angle for smooth maneuvering.")
    parser.add_argument("--metrics_log_sec", type=float, default=1.5, help="Seconds between Falcon quality metric logs.")
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

    args = parser.parse_args()
    if args.offline:
        collect_data_offline(args)
    else:
        asyncio.run(collect_data(args))


