import airsim
import time
import numpy as np

# --- Step 3: The Simplest Avoidance ---
# Builds on move_with_perception.py.
# If the path ahead is blocked, it stops and turns right.
# Otherwise, it moves forward.

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

        # 4. Avoidance Loop
        print("[INFO] Starting 10 second pure forward test with perception diagnostics...")

        FORWARD_SPEED = 3.0  # m/s
        LOOP_DURATION = 0.7  # seconds per command

        start_time = time.time()
        while time.time() - start_time < 10.0:
            # Get depth image
            responses = client.simGetImages([
                airsim.ImageRequest("0", airsim.ImageType.DepthPerspective, True, False)
            ])

            if not responses or not responses[0].pixels_as_float:
                print("[WARN] No valid depth data received. Skipping frame.")
                time.sleep(0.2)
                continue

            # Get depth values in the center row
            depth_image = airsim.get_pfm_array(responses[0])
            h, w = depth_image.shape
            center_row = depth_image[h//2, :]
            min_center = float(np.nanmin(center_row))
            mean_center = float(np.nanmean(center_row))
            center_distance = center_row[w//2]

            # Print position BEFORE move
            pose_before = client.simGetVehiclePose()
            print(f"[DBG] BEFORE MOVE: t={time.time()-start_time:.1f}s pos=({pose_before.position.x_val:.2f}, {pose_before.position.y_val:.2f}, {pose_before.position.z_val:.2f}) center_depth={center_distance:.2f}m min_center={min_center:.2f} mean_center={mean_center:.2f}")

            # Pure forward motion, hold altitude at z = -1.0
            TARGET_ALTITUDE = -1.0
            client.moveByVelocityZAsync(
                vx=FORWARD_SPEED,     # Move forward at 3 m/s
                vy=0,
                z=TARGET_ALTITUDE,
                duration=LOOP_DURATION,
                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=0)
            ).join()

            # Print position AFTER move
            pose_after = client.simGetVehiclePose()
            print(f"[DBG] AFTER MOVE:  t={time.time()-start_time:.1f}s pos=({pose_after.position.x_val:.2f}, {pose_after.position.y_val:.2f}, {pose_after.position.z_val:.2f})")

            # Print velocity
            kinematics = client.getMultirotorState().kinematics_estimated
            vel = kinematics.linear_velocity
            print(f"[DBG] VELOCITY: vx={vel.x_val:.2f}, vy={vel.y_val:.2f}, vz={vel.z_val:.2f}")

            # Print collision info if available
            collision = client.simGetCollisionInfo()
            if collision.has_collided:
                print(f"[DBG] COLLISION DETECTED at pos=({collision.position.x_val:.2f}, {collision.position.y_val:.2f}, {collision.position.z_val:.2f})")

            time.sleep(0.1) # Loop at ~10Hz

        print("[SUCCESS] Avoidance loop finished.")
        
        # Confirm final position
        pose = client.simGetVehiclePose()
        print(f"[INFO] Final position: x={pose.position.x_val:.2f}, y={pose.position.y_val:.2f}, z={pose.position.z_val:.2f}")

    except Exception as e:
        print(f"[ERROR] An error occurred during flight: {e}")
    
    finally:
        # 5. Land and disarm
        print("[INFO] Cleaning up: landing and disarming...")
        client.hoverAsync().join()
        client.landAsync().join()
        client.armDisarm(False)
        client.enableApiControl(False)
        print("[COMPLETE] Script finished.")


if __name__ == "__main__":
    main()
