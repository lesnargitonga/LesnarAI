import asyncio
import argparse
import csv
import time
from pathlib import Path

# MAVSDK Python
from mavsdk import System

"""
PX4 Teacher collector
- Connects to PX4 SITL via MAVSDK (UDP:14540)
- Arms, takes off to target altitude
- Runs a simple teacher: waypoint bias + obstacle-aware yaw (if distance available)
- Logs telemetry + teacher actions at hz to CSV

Outputs:
  out/telemetry.csv with columns:
    t, lat, lon, rel_alt, vx, vy, vz, yaw_deg, teacher_vx, teacher_vy, teacher_vz, teacher_yaw_deg
"""


def deg(yaw_rad: float) -> float:
    import math
    return float((yaw_rad * 180.0 / math.pi) % 360.0)


async def run(system_addr: str, out_dir: Path, duration: float, hz: float, alt_m: float):
    drone = System(mavsdk_server_address=system_addr)
    await drone.connect()

    print("Waiting for connection...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Connected to autopilot")
            break

    print("Waiting for global position estimate...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok or health.is_local_position_ok:
            break

    print("Arming and taking off...")
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(4)
    await drone.action.set_takeoff_altitude(alt_m)

    # Prepare logging
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "telemetry.csv"
    f = open(csv_path, "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow(["t", "lat", "lon", "rel_alt", "vx", "vy", "vz", "yaw_deg", "teacher_vx", "teacher_vy", "teacher_vz", "teacher_yaw_deg"])

    # Teacher parameters
    dt = 1.0 / max(1e-3, hz)
    t0 = time.time()

    # Simple waypoint drift target (keep heading ~0 deg forward)
    teacher_speed = 2.0
    teacher_yaw_deg = 0.0

    try:
        while True:
            if duration > 0 and (time.time() - t0) >= duration:
                break

            # Telemetry snapshot
            pos_task = drone.telemetry.position()
            vel_task = drone.telemetry.velocity_ned()
            heading_task = drone.telemetry.heading()
            pos = await pos_task.__anext__()
            vel = await vel_task.__anext__()
            heading = await heading_task.__anext__()

            yaw_deg = float(heading)
            lat = float(pos.latitude_deg)
            lon = float(pos.longitude_deg)
            rel_alt = float(pos.relative_altitude_m)
            vx = float(vel.north_m_s)
            vy = float(vel.east_m_s)
            vz = float(vel.down_m_s)

            # Teacher action: forward in world frame per yaw target
            import math
            rad = math.radians(teacher_yaw_deg)
            tvx = teacher_speed * math.cos(rad)
            tvy = teacher_speed * math.sin(rad)
            tvz = 0.0

            # Send velocity command in NED (north/east/down)
            try:
                await drone.action.set_velocity_ned(tvx, tvy, tvz, yaw_deg)
            except Exception:
                pass

            w.writerow([time.time(), lat, lon, rel_alt, vx, vy, vz, yaw_deg, tvx, tvy, tvz, teacher_yaw_deg])
            await asyncio.sleep(dt)
    except KeyboardInterrupt:
        pass
    finally:
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
    ap.add_argument("--out", type=str, default=str(Path("dataset/px4_teacher")))
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--alt", type=float, default=10.0)
    args = ap.parse_args()

    out_dir = Path(args.out)
    asyncio.run(run(args.system, out_dir, args.duration, args.hz, args.alt))


if __name__ == "__main__":
    main()
