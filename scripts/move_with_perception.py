import airsim
import time
import numpy as np

# --- Step 2: Move with Perception ---
# Builds on simple_move.py.
# Moves forward while also fetching depth camera data.
# This proves that perception and motion can run together.

def main():
    # 1. Connect to AirSim
    client = airsim.MultirotorClient()
    try:
        client.confirmConnection()
        print("[SUCCESS] Connected to AirSim.")
    except Exception as e:
        print(f"[ERROR] Connection to AirSim failed: {e}")
        print("Please make sure AirSim is running and in 'Play' mode.")
        return

    try:
        # 2. Enable API control and arm
        client.enableApiControl(True)
        client.armDisarm(True)
        print("[INFO] API control enabled, drone armed.")

        # 3. Take off
        print("[INFO] Taking off...")
        client.takeoffAsync(timeout_sec=15).join()
        time.sleep(2)
        
        pose = client.simGetVehiclePose()
        print(f"[INFO] Position after takeoff: x={pose.position.x_val:.2f}, y={pose.position.y_val:.2f}, z={pose.position.z_val:.2f}")

        # 4. Move Forward while Perceiving
        print("[INFO] Moving forward at 2 m/s for 5 seconds while fetching depth images...")
        
        start_time = time.time()
        while time.time() - start_time < 5.0:
            # Command continuous forward motion
            client.moveByVelocityAsync(vx=2, vy=0, vz=0, duration=1.0)
            
            # While moving, request a depth image
            responses = client.simGetImages([
                # "0" is the default front-facing camera
                # ImageType.DepthPerspective gives depth in meters
                airsim.ImageRequest("0", airsim.ImageType.DepthPerspective, True, False)
            ])
            
            response = responses[0]
            
            if response.pixels_as_float:
                # If we got depth data, print its stats
                depth_image = airsim.get_pfm_array(response)
                print(f"[PERCEPTION] Got depth image. Shape: {depth_image.shape}, Min: {np.min(depth_image):.2f}m, Max: {np.max(depth_image):.2f}m")
            else:
                print("[PERCEPTION] Got image, but not in expected float format.")

            time.sleep(0.2) # Loop at ~5Hz

        print("[SUCCESS] Movement with perception completed.")
        
        # Confirm position after moving
        pose = client.simGetVehiclePose()
        print(f"[INFO] Position after moving: x={pose.position.x_val:.2f}, y={pose.position.y_val:.2f}, z={pose.position.z_val:.2f}")

    except Exception as e:
        print(f"[ERROR] An error occurred during flight: {e}")
    
    finally:
        # 5. Land and disarm
        print("[INFO] Cleaning up: landing and disarming...")
        # Use hover to stabilize before landing
        client.hoverAsync().join()
        client.landAsync().join()
        client.armDisarm(False)
        client.enableApiControl(False)
        print("[COMPLETE] Script finished.")


if __name__ == "__main__":
    main()
