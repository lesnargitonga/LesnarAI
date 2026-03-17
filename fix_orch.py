import re

with open("scripts/runtime_orchestrator.py", "r") as f:
    content = f.read()

new_spawn = """    # 3. Spawn Drones
    for i in range(drone_count):
        px4_env = os.environ.copy()
        px4_env["PX4_GZ_STANDALONE"] = "1"
        px4_env["PX4_GZ_WORLD"] = "obstacles"
        # We enforce exactly the user's process per their explicit request
        cmd = f"nohup make px4_sitl gz_x500 > {REPO_DIR}/logs/px4_{i}.out 2>&1 &"
        subprocess.Popen(cmd, shell=True, cwd=PX4_DIR, env=px4_env)
        time.sleep(3)"""

content = re.sub(r'    # 3\. Spawn Drones.*?(?=    # 4\. Start Teacher Bridge)', new_spawn + '\n\n', content, flags=re.DOTALL)

with open("scripts/runtime_orchestrator.py", "w") as f:
    f.write(content)
