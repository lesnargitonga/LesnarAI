#!/usr/bin/env python3
"""
Direct drone spawn - bypasses PX4's gz_bridge timeout issues
"""
import subprocess
import time
import sys

def run_cmd(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    return result.stdout

# Step 1: Start Gazebo with obstacles world (no PX4 yet)
print("Starting Gazebo...")
subprocess.Popen(
    ['gz', 'sim', '-v4', '-r', f'{os.path.expanduser("~")}/workspace/LesnarAI/obstacles.sdf'],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

# Wait for Gazebo to be ready
print("Waiting for Gazebo world...")
for i in range(30):
    if '/world/obstacles' in run_cmd('gz topic -l 2>/dev/null', False):
        print("✓ Gazebo ready")
        break
    time.sleep(0.5)
else:
    print("✗ Gazebo timeout")
    sys.exit(1)

# Step 2: Directly spawn drone using gz service
print("Spawning drone...")
px4_x500_sdf = f'{os.path.expanduser("~")}/PX4-Autopilot/Tools/simulation/gz/models/x500/model.sdf'
with open(px4_x500_sdf) as f:
    sdf_content = f.read()

# Create spawn request
spawn_req =f'''
sdf: "{sdf_content.replace('"', '\\"').replace(chr(10), ' ')}"
name: "x500_0"
pose {{
  position {{ x: 0 y: 0 z: 2.5 }}
}}
'''

result = run_cmd(
    f"echo '{spawn_req}' | gz service -s /world/obstacles/create "
    f"--reqtype gz.msgs.EntityFactory --reptype gz.msgs.Boolean",
    False
)

if 'true' in result.lower():
    print("✓ Drone spawned")
else:
    print(f"✗ Spawn failed: {result}")
    sys.exit(1)

# Step 3: Now start PX4 to connect to existing drone
print("Starting PX4 autopilot...")
import os
os.chdir(os.path.expanduser('~/PX4-Autopilot'))
os.environ['PX4_GZ_MODEL_NAME'] = 'x500_0'
os.environ['PX4_GZ_WORLD'] = 'obstacles'

subprocess.run(['build/px4_sitl_default/bin/px4', '-d', 'build/px4_sitl_default/etc', '-s', 'etc/init.d-posix/rcS'])
