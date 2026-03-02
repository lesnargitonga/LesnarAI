import asyncio
import sys
import shutil
from mavsdk import System
from mavsdk.telemetry import FlightMode

# Global State Dictionary to hold latest telemetry
STATE = {
    'pos': None, 
    'vel': None, 
    'att': None, 
    'batt': 0.0, 
    'mode': "UNKNOWN", 
    'lidar': None, 
    'gps': None
}

def print_dashboard(pos, vel, att, batt, mode, lidar, gps):
    # Clear screen
    print("\033[H\033[J", end="")
    
    width = 60
    print("=" * width)
    print(f"   LESNAR AI - DRONE MONITOR (WSL/Gazebo)   ")
    print("=" * width)
    
    print(f" Status:      {'CONNECTED' if pos else 'WAITING...'}")
    print(f" Flight Mode: {mode}")
    print(f" Battery:     {batt:.1f} V")
    print("-" * width)
    
    if pos:
        print(f" Position:")
        print(f"   Lat: {pos.latitude_deg:.6f}")
        print(f"   Lon: {pos.longitude_deg:.6f}")
        print(f"   Alt: {pos.relative_altitude_m:.1f} m (Rel)")
    
    if vel:
        speed = (vel.north_m_s**2 + vel.east_m_s**2)**0.5
        print(f" Velocity:")
        print(f"   North: {vel.north_m_s:.1f} m/s")
        print(f"   East:  {vel.east_m_s:.1f} m/s")
        print(f"   Down:  {vel.down_m_s:.1f} m/s")
        print(f"   Speed: {speed:.1f} m/s")

    print("-" * width)
    if lidar:
        # Filter out invalid readings (0 or very large) if necessary
        valid_dists = [x for x in lidar.distances if x > 0 and x < 40]
        min_dist = min(valid_dists) if valid_dists else 999.0
        print(f" LIDAR 360 (Blind Bat Eye):")
        print(f"   Min Dist: {min_dist:.2f} m")
        print(f"   Points:   {len(valid_dists)}")
    else:
        print(" LIDAR: No Data (Waiting for sensor...)")

    print("-" * width)
    print(" Press Ctrl+C to exit")

# Async update functions
async def update_pos(drone):
    async for x in drone.telemetry.position(): STATE['pos'] = x

async def update_vel(drone):
    async for x in drone.telemetry.velocity_ned(): STATE['vel'] = x

async def update_batt(drone):
    async for x in drone.telemetry.battery(): STATE['batt'] = x.voltage_v

async def update_mode(drone):
    async for x in drone.telemetry.flight_mode(): STATE['mode'] = str(x)

async def update_lidar(drone):
    async for x in drone.telemetry.obstacle_distance(): STATE['lidar'] = x

async def main():
    drone = System()
    print("Connecting to drone on udp://:14540 ...")
    await drone.connect(system_address="udp://:14540")
    
    print("Connected! Waiting for telemetry...")
    
    # Start background tasks
    asyncio.create_task(update_pos(drone))
    asyncio.create_task(update_vel(drone))
    asyncio.create_task(update_batt(drone))
    asyncio.create_task(update_mode(drone))
    asyncio.create_task(update_lidar(drone))
    
    # Main dashboard loop
    while True:
        print_dashboard(
            STATE['pos'], 
            STATE['vel'], 
            STATE['att'], 
            STATE['batt'], 
            STATE['mode'], 
            STATE['lidar'], 
            STATE['gps']
        )
        await asyncio.sleep(0.2)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
