
import os
import json
import time

SHARED_MISSION_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared', 'mission_override.json')

def send_mission_override(x: float, y: float, z: float, cmd: str = "NAVIGATE"):
    """Writes a command to the shared file for the RL brain to pick up."""
    data = {
        "timestamp": time.time(),
        "command": cmd,
        "target": [x, y, z]
    }
    os.makedirs(os.path.dirname(SHARED_MISSION_PATH), exist_ok=True)
    with open(SHARED_MISSION_PATH, "w") as f:
        json.dump(data, f)
    print(f"[AirSimAdapter] Sent override: {data}")
