"""
Main entry point for the Lesnar AI Drone Simulation
"""

import sys
import time
import signal
from simulator import DroneFleet, Mission

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nShutting down drone simulation...")
    global fleet
    if fleet:
        for drone_id in list(fleet.drones.keys()):
            fleet.remove_drone(drone_id)
    sys.exit(0)

def main():
    """Main simulation entry point"""
    global fleet
    
    print("=== Lesnar AI Drone Simulation System ===")
    print("Advanced AI-enabled drone automation platform")
    print("Copyright © 2025 Lesnar AI Ltd.")
    print("-" * 45)
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize drone fleet
    fleet = DroneFleet()
    
    # Add demonstration drones
    print("Initializing drone fleet...")
    fleet.add_drone("LESNAR-ALPHA", (40.7128, -74.0060, 0))    # NYC
    fleet.add_drone("LESNAR-BETA", (40.7589, -73.9851, 0))     # Times Square area
    fleet.add_drone("LESNAR-GAMMA", (40.6892, -74.0445, 0))    # Statue of Liberty area
    
    print("Drone fleet initialized with 3 drones")
    print("\nStarting demonstration sequence...")
    
    # Demonstration sequence
    try:
        # Get drones
        alpha = fleet.get_drone("LESNAR-ALPHA")
        beta = fleet.get_drone("LESNAR-BETA")
        gamma = fleet.get_drone("LESNAR-GAMMA")
        
        # Demo 1: Basic takeoff and navigation
        print("\n--- Demo 1: Basic Flight Operations ---")
        alpha.arm()
        alpha.takeoff(20.0)
        
        # Wait for takeoff
        time.sleep(3)
        
        # Navigate to Central Park
        alpha.goto(40.7829, -73.9654, 25.0)
        
        # Demo 2: Multi-drone coordination
        print("\n--- Demo 2: Multi-drone Operations ---")
        beta.arm()
        beta.takeoff(15.0)
        gamma.arm()
        gamma.takeoff(18.0)
        
        time.sleep(2)
        
        # Formation flying to Brooklyn Bridge area
        beta.goto(40.7061, -73.9969, 20.0)
        gamma.goto(40.7031, -73.9969, 22.0)
        
        # Demo 3: Mission execution
        print("\n--- Demo 3: Mission Execution ---")
        patrol_mission = Mission(
            waypoints=[
                (40.7505, -73.9934, 25.0),  # Times Square
                (40.7614, -73.9776, 25.0),  # Central Park South
                (40.7489, -73.9680, 25.0),  # UN Headquarters
                (40.7128, -74.0060, 25.0),  # Back to start
            ],
            mission_type="PATROL",
            estimated_duration=600.0
        )
        
        alpha.execute_mission(patrol_mission)
        
        # Monitor all drones for 30 seconds
        print("\n--- Real-time Monitoring ---")
        print("Monitoring drone fleet (30 seconds)...")
        
        for i in range(30):
            states = fleet.get_all_states()
            print(f"\n--- Update {i+1}/30 ---")
            
            for state in states:
                print(f"{state.drone_id}: "
                      f"Alt={state.altitude:.1f}m, "
                      f"Speed={state.speed:.1f}m/s, "
                      f"Battery={state.battery:.1f}%, "
                      f"Mode={state.mode}")
            
            time.sleep(1)
        
        # Demo 4: Emergency procedures
        print("\n--- Demo 4: Emergency Landing ---")
        fleet.emergency_land_all()
        
        # Monitor landing
        print("Monitoring emergency landing...")
        for i in range(10):
            states = fleet.get_all_states()
            all_landed = True
            
            print(f"\n--- Landing Update {i+1}/10 ---")
            for state in states:
                print(f"{state.drone_id}: "
                      f"Alt={state.altitude:.1f}m, "
                      f"Mode={state.mode}")
                if state.altitude > 0.5:
                    all_landed = False
            
            if all_landed:
                print("All drones have landed successfully!")
                break
            
            time.sleep(1)
        
    except Exception as e:
        print(f"Error during demonstration: {e}")
    
    finally:
        print("\nShutting down simulation...")
        for drone_id in list(fleet.drones.keys()):
            fleet.remove_drone(drone_id)
        print("Simulation complete!")

if __name__ == "__main__":
    main()
