import asyncio
import argparse
import csv
import json
import math
import time
from pathlib import Path

from mavsdk import System


"""
Advanced PX4 Teacher Collector (Offboard)

- Connects to PX4 via MAVSDK (UDP:14540)
- Arms, takeoffs, switches to Offboard
- Follows waypoints (lat/lon) with smooth yaw control
- Uses obstacle distance (if available) to bias yaw away from close obstacles
- Logs state + teacher actions at high rate for distillation

CSV columns:
  t, lat, lon, rel_alt, vx, vy, vz, yaw_deg,
  teacher_vx, teacher_vy, teacher_vz, teacher_yaw_deg,
  wp_lat, wp_lon, wp_idx, obs_min, obs_left, obs_right

Notes:
  - Requires MAVSDK Python (`pip install mavsdk`).
  - Obstacle distances rely on PX4 sending OBSTACLE_DISTANCE (e.g., via companion/ROS). If not present, the script falls back to waypoint-only yaw.
"""


def wrap_deg(a):
    a = a % 360.0
    if a < 0:
        a += 360.0
    return float(a)


def shortest_diff(a, b):
    return ((b - a + 540) % 360) - 180


def haversine_m(lat1, lon1, lat2, lon2):
    import math
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


async def collect(system_addr: str, out_dir: Path, waypoints_file: Path, duration: float, hz: float, alt_m: float,
                  base_speed: float, max_speed: float, yaw_rate_limit_deg_s: float):
    # Fix: system_addr is for MAVLink connection, not gRPC server address
    drone = System()
    await drone.connect(system_address=system_addr)

    print("Waiting for connection...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            break
    print("Connected")

    print("Waiting for position...")
    async for health in drone.telemetry.health():
        if health.is_local_position_ok or health.is_global_position_ok:
            break

    # Load waypoints
    with open(waypoints_file, "r", encoding="utf-8") as f:
        wps = json.load(f).get("waypoints", [])
    if not wps:
        raise RuntimeError("No waypoints provided")

    # Arm, takeoff
    await drone.action.arm()
    await drone.action.set_takeoff_altitude(alt_m)
    await drone.action.takeoff()
    await asyncio.sleep(3)

    # Start offboard with zero velocity
    from mavsdk.offboard import (OffboardError, VelocityNedYaw)
    try:
        await drone.offboard.start()
    except OffboardError:
        # PX4 requires an initial setpoint before start
        await drone.offboard.set_velocity_ned(VelocityNedYaw(0.0, 0.0, 0.0, 0.0))
        await drone.offboard.start()

    # Logging
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "telemetry_adv.csv"
    f = open(csv_path, "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow(["t", "lat", "lon", "rel_alt", "vx", "vy", "vz", "yaw_deg",
                "teacher_vx", "teacher_vy", "teacher_vz", "teacher_yaw_deg",
                "wp_lat", "wp_lon", "wp_idx", "obs_min", "obs_left", "obs_right"])

    # Teacher state
    dt = 1.0 / max(1e-3, hz)
    t0 = time.time()
    wp_idx = 0
    yaw_deg = 0.0
    yaw_ema = 0.0
    speed_ema = 0.0

    try:
        while True:
            if duration > 0 and (time.time() - t0) >= duration:
                break

            # Telemetry
            pos_task = drone.telemetry.position()
            vel_task = drone.telemetry.velocity_ned()
            heading_task = drone.telemetry.heading()
            pos = await pos_task.__anext__()
            vel = await vel_task.__anext__()
            heading = await heading_task.__anext__()
            lat = float(pos.latitude_deg)
            lon = float(pos.longitude_deg)
            rel_alt = float(pos.relative_altitude_m)
            vx = float(vel.north_m_s)
            vy = float(vel.east_m_s)
            vz = float(vel.down_m_s)
            yaw_deg = float(heading.heading_deg)

            # Current waypoint target
            wp = wps[wp_idx]
            dist_m = haversine_m(lat, lon, float(wp["lat"]), float(wp["lon"]))
            # Advance waypoint on close
            if dist_m < 3.0:
                wp_idx = (wp_idx + 1) % len(wps)
                wp = wps[wp_idx]

            # Desired bearing to waypoint
            bearing = math.degrees(math.atan2(float(wp["lon"]) - lon, float(wp["lat"]) - lat))

            # Obstacle distance (if available)
            obs_min = math.nan; obs_left = math.nan; obs_right = math.nan
            try:
                obs_task = drone.telemetry.obstacle_distance()
                obs = await obs_task.__anext__()
                # obs.distances is a list of 72 values (typically), covering -90..+90 deg or full circle depending on sensor
                ds = list(obs.distances)
                if ds:
                    obs_min = float(min([d for d in ds if d > 0])) if any(d > 0 for d in ds) else math.nan
                    mid = len(ds) // 2
                    obs_left = float(min(ds[:mid])) if any(d > 0 for d in ds[:mid]) else math.nan
                    obs_right = float(min(ds[mid:])) if any(d > 0 for d in ds[mid:]) else math.nan
            except Exception:
                pass

            # Teacher yaw: blend toward waypoint bearing, bias away from close obstacles
            target_yaw = bearing
            if math.isfinite(obs_left) and math.isfinite(obs_right):
                # Push away from closer side
                bias = (obs_right - obs_left)
                target_yaw = wrap_deg(target_yaw + max(-20.0, min(20.0, 0.5 * bias)))

            # Rate-limit yaw change
            diff = shortest_diff(yaw_deg, target_yaw)
            step = max(-yaw_rate_limit_deg_s * dt, min(yaw_rate_limit_deg_s * dt, diff))
            teacher_yaw_deg = wrap_deg(yaw_deg + step)

            # Speed schedule: speed up when far from waypoint, slow near
            sp = base_speed + max(0.0, min(1.0, dist_m / 20.0)) * (max_speed - base_speed)
            # EMA smoothing
            yaw_ema = 0.6 * teacher_yaw_deg + 0.4 * yaw_ema
            speed_ema = 0.6 * sp + 0.4 * speed_ema

            # Command velocity in NED
            rad = math.radians(yaw_ema)
            tvx = speed_ema * math.cos(rad)
            tvy = speed_ema * math.sin(rad)
            tvz = 0.0
            from mavsdk.offboard import VelocityNedYaw
            try:
                await drone.offboard.set_velocity_ned(VelocityNedYaw(float(tvx), float(tvy), float(tvz), float(yaw_ema)))
            except Exception:
                pass

            # Log row
            w.writerow([time.time(), lat, lon, rel_alt, vx, vy, vz, yaw_deg,
                        tvx, tvy, tvz, teacher_yaw_deg,
                        float(wp["lat"]), float(wp["lon"]), wp_idx, obs_min, obs_left, obs_right])
            await asyncio.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            await drone.offboard.stop()
        except Exception:
            pass
        try:
            await drone.action.hold()
            await drone.action.land()
        except Exception:
            pass
        f.close()
        print(f"Saved telemetry to {csv_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", type=str, default="127.0.0.1:14540")
    ap.add_argument("--waypoints", type=str, default=str(Path("training/px4_waypoints.json")))
    ap.add_argument("--out", type=str, default=str(Path("dataset/px4_teacher")))
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--hz", type=float, default=20.0)
    ap.add_argument("--alt", type=float, default=10.0)
    ap.add_argument("--base_speed", type=float, default=2.0)
    ap.add_argument("--max_speed", type=float, default=5.0)
    ap.add_argument("--yaw_rate_limit", type=float, default=45.0)
    args = ap.parse_args()

    out_dir = Path(args.out)
    waypoints_file = Path(args.waypoints)
    asyncio.run(collect(args.system, out_dir, waypoints_file, args.duration, args.hz, args.alt, args.base_speed, args.max_speed, args.yaw_rate_limit))


if __name__ == "__main__":
    main()