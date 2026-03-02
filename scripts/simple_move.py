import airsim
import time

# --- The Simplest Move Script ---
# Connects, takes off, moves forward in a straight line for 5 seconds, then lands.
# No avoidance, no complex commands. Just raw motion.

def main():
    # 1. Connect to AirSim
    client = airsim.MultirotorClient()
    try:
        client.confirmConnection()
        print("[SUCCESS] Connected to AirSim.")
    except Exception as e:
        print(f"[ERROR] Connection to AirSim failed: {e}")
        print("Please make sure AirSim is running and in 'Play' mode in the Unreal Editor.")
        return

    try:
        # 2. Enable API control and arm the drone
        client.enableApiControl(True)
        client.armDisarm(True)
        print("[INFO] API control enabled, drone armed.")

        # 3. Take off
        print("[INFO] Taking off...")
        # Using takeoffAsync().join() is a reliable way to ensure takeoff completes.
        client.takeoffAsync(timeout_sec=15).join()
        
        # Wait a moment to stabilize after takeoff before moving.
        time.sleep(2)
        
        # Confirm current position
        pose = client.simGetVehiclePose()
        print(f"[INFO] Position after takeoff: x={pose.position.x_val:.2f}, y={pose.position.y_val:.2f}, z={pose.position.z_val:.2f}")

        # 4. Move Forward
        print("[INFO] Moving forward at 2 m/s for 5 seconds...")
        # moveByVelocityAsync is the most direct way to command motion.
        # vx=2 means 2 m/s along the drone's forward-facing axis (X).
        # duration=5 means the command will be active for 5 seconds.
        client.moveByVelocityAsync(vx=2, vy=0, vz=0, duration=5).join()
        
        # Wait a moment for the movement to fully stop.
        time.sleep(1)

        # Confirm position after moving
        pose = client.simGetVehiclePose()
        print(f"[INFO] Position after moving: x={pose.position.x_val:.2f}, y={pose.position.y_val:.2f}, z={pose.position.z_val:.2f}")
        print("[SUCCESS] Movement command completed.")

    except Exception as e:
        print(f"[ERROR] An error occurred during flight: {e}")
    
    finally:
        # 5. Land and disarm
        print("[INFO] Cleaning up: landing and disarming...")
        client.landAsync().join()
        client.armDisarm(False)
        client.enableApiControl(False)
        print("[COMPLETE] Script finished.")


if __name__ == "__main__":
    main()
