import airsim
import json
import os
import math
import argparse
import time

def spawn_obstacles(obstacles_file):
    client = airsim.MultirotorClient()
    client.confirmConnection()
    
    print(f"Loading obstacles from {obstacles_file}...")
    with open(obstacles_file, 'r') as f:
        config = json.load(f)
        
    obstacles = config.get("obstacles", [])
    name_prefix = config.get("name_prefix", "LESNAR_GEN_")
    
    # Global offsets
    off_x = float(config.get("obstacle_offset_x_m", 0.0))
    off_y = float(config.get("obstacle_offset_y_m", 0.0))
    off_z = float(config.get("obstacle_offset_z_m_ned", 0.0))
    
    scale_floor = config.get("scale_floor", False)
    if scale_floor:
        # Just spawn a floor if it doesn't exist? 
        # Usually floor is already there. The script in Unreal scales it. 
        # We can try to find 'Floor' and scale it if needed, but skipping for now.
        pass

    spawned_count = 0
    
    current_objects = client.simListSceneObjects(f"{name_prefix}.*")
    print(f"Found {len(current_objects)} existing obstacles matching prefix '{name_prefix}'")
    
    # We might want to destroy existing ones to update positions
    # for name in current_objects:
    #    client.simDestroyObject(name)
    #    print(f"Destroyed {name}")

    for obs in obstacles:
        name = obs.get("name", "Unknown")
        full_name = f"{name_prefix}{name}"
        
        # Check if already exists
        if full_name in current_objects:
            print(f"Skipping {full_name} (already exists)")
            # Optional: Update pose/scale if it exists?
            # client.simDestroyObject(full_name)
            continue
            
        asset = obs.get("asset", "/Engine/BasicShapes/Cube.Cube")
        # For simple cubes, AirSim might expect "Cube" or similar depending on the environment assets.
        # But if the user environment has these paths, we use them.
        # Note: simSpawnObject might require just "Cube" if it's a basic shape not needing full path?
        # Let's try to use the asset name provided.

        # Coordinates
        x = float(obs.get("x_m", 0.0)) + off_x
        y = float(obs.get("y_m", 0.0)) + off_y
        z = float(obs.get("z_m_ned", 0.0)) + off_z
        
        yaw_deg = float(obs.get("yaw_deg", 0.0))
        
        # Scale
        if "scale" in obs:
            sx = sy = sz = float(obs.get("scale"))
        else:
            sx = float(obs.get("scale_x", 1.0))
            sy = float(obs.get("scale_y", 1.0))
            sz = float(obs.get("scale_z", 1.0))
            
        pose = airsim.Pose(airsim.Vector3r(x, y, z), airsim.to_quaternion(0, 0, math.radians(yaw_deg)))
        scale = airsim.Vector3r(sx, sy, sz)
        
        try:
             # asset_name often needs to be just the name if it is a blueprint in contents, 
             # OR a full path. The JSON has "/Engine/BasicShapes/Cube.Cube".
             # If this fails, we might try "Cube".
             final_name = client.simSpawnObject(full_name, "Cube", pose, scale, physics_enabled=False)
             # Note: Using "Cube" as asset_name because typically that's the key for the basic cube in AirSim.
             # If the JSON specifically meant a different asset, we should use it. 
             # But "Cube.Cube" suggests a StaticMesh which simSpawnObject might not handle directly if it expects a Blueprint?
             # Actually docs say "asset_name... Name of asset(mesh) in the project database".
             # Start with "Cube" which is standard.
             
             if final_name != full_name:
                 print(f"Warning: Spawned as {final_name} instead of {full_name}")
                 # Rename or track?
             
             # Enforce scale (spawn might usually ignore scale intially or apply default)
             client.simSetObjectScale(final_name, scale)
             
             print(f"Spawned {final_name} at ({x:.1f}, {y:.1f}, {z:.1f})")
             spawned_count += 1
             
        except Exception as e:
            print(f"Failed to spawn {full_name}: {e}")
            
    print(f"Done. Spawned {spawned_count} new obstacles.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Default relative to this script
    default_json = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "unreal_tools", "ue_obstacles.blocks.json")
    parser.add_argument("--file", default=default_json)
    args = parser.parse_args()
    
    spawn_obstacles(args.file)
