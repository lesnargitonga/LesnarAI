"""
Professional Inference Script for Lesnar AI (Genius/SOTA Edition).
Loads the trained RecurrentPPO (LSTM) model and flies the drone in AirSim.
No noise, no training - just pure execution.
"""

import time
import argparse
import numpy as np
import cv2
import torch
import airsim
from sb3_contrib import RecurrentPPO

# Import the environment class (must match training exactly)
from airsim_gym_env import AirSimDroneEnv, EnvConfig

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, required=True, help="Path to .zip model file")
    ap.add_argument("--hz", type=float, default=20.0, help="Control loop rate")
    return ap.parse_args()

def main():
    args = parse_args()

    # 1. Initialize Environment (Inference Mode)
    # Note: We disable Domain Randomization for the "Test Flight" to see pure performance
    cfg = EnvConfig(
        hz=args.hz,
        enable_domain_randomization=False, # Pure flight
        vehicle_name=""
    )
    
    print("[Lesnar AI] Connecting to Drone...")
    env = AirSimDroneEnv(config=cfg)
    
    # 2. Load the Brain
    print(f"[Lesnar AI] Loading Neural Network from {args.model}...")
    try:
        model = RecurrentPPO.load(args.model, device="cuda" if torch.cuda.is_available() else "cpu")
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    # 3. Flight Loop
    obs, info = env.reset()
    
    # Initialize LSTM states (Short-Term Memory)
    # The LSTM needs a hidden state (h) and cell state (c). 
    # SB3 manages this, but we must pass them in the unpredictable loop.
    lstm_states = None
    
    # Start of Episode flags
    episode_starts = np.ones((1,), dtype=bool)

    print("[Lesnar AI] taking off... (Press Ctrl+C to stop)")
    
    try:
        while True:
            start_time = time.time()
            
            # AI Inference
            # deterministic=True means "Don't explore, do the best action you know"
            action, lstm_states = model.predict(
                obs, 
                state=lstm_states, 
                episode_start=episode_starts, 
                deterministic=True
            )
            
            # Execute Action
            obs, reward, terminated, truncated, info = env.step(action[0])
            episode_starts = np.array([terminated or truncated])

            # Visualization (Optional)
            # You can see what the drone sees
            if "visual" in obs:
                 # Reshape from (1, 84, 84) -> (84, 84)
                 depth_map = obs["visual"][0]
                 cv2.imshow("Drone Vision (Depth)", depth_map)
                 if cv2.waitKey(1) & 0xFF == ord('q'):
                     break
            
            # Print Telemetry
            vel = info.get('velocity', 0.0)
            print(f"Vel: {vel:.2f} m/s | Action: {action[0]}", end="\r")
            
            if terminated or truncated:
                print("\n[Lesnar AI] Crash/Reset detected. Restarting mission...")
                obs, info = env.reset()
                lstm_states = None
                episode_starts = np.ones((1,), dtype=bool)

            # Loop Rate Enforcement is handled inside env.step() now via our patch
            
    except KeyboardInterrupt:
        print("\n[Lesnar AI] Landing...")
    finally:
        env.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
