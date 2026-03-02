"""
Benchmark Script to find the AirSim Bottleneck.
"""
import airsim
import time
import numpy as np

def benchmark():
    client = airsim.MultirotorClient()
    client.confirmConnection()
    
    print("Testing 100 iterations of sensor capture...")
    
    # 1. Image Capture
    start = time.time()
    for _ in range(100):
        client.simGetImages([
            airsim.ImageRequest("0", airsim.ImageType.DepthPerspective, pixels_as_float=True, compress=False)
        ])
    img_time = (time.time() - start) / 100.0
    print(f"Image Capture: {img_time*1000:.2f} ms per frame")
    
    # 2. Kinematics
    start = time.time()
    for _ in range(100):
        client.getMultirotorState()
    kin_time = (time.time() - start) / 100.0
    print(f"Kinematics: {kin_time*1000:.2f} ms per frame")

    # 3. Control
    start = time.time()
    for _ in range(100):
        client.moveByVelocityZBodyFrameAsync(0, 0, -2, 0.05).join()
    ctrl_time = (time.time() - start) / 100.0
    print(f"Control (Blocking): {ctrl_time*1000:.2f} ms per frame")

if __name__ == "__main__":
    benchmark()
