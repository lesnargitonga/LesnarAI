import subprocess
import socket
import sys
import os
import urllib.request
import json

def log(msg, status="INFO"):
    print(f"[{status}] {msg}")

def check_command(command):
    try:
        subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False

def check_port(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0

def check_url(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.getcode() == 200
    except Exception as e:
        log(f"Failed to reach {url}: {e}", "WARN")
        return False

def check_package(package_name):
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def main():
    log("Starting System Diagnosis...")

    # 1. Docker Check
    if check_command("docker --version"):
        log("Docker is installed.", "PASS")
        if check_command("docker ps"):
            log("Docker daemon is running.", "PASS")
            
            # Check specific containers
            containers = ["timescaledb", "redis", "lesnar-ai-backend-1"] # Adjust backend name if needed
            running_containers = subprocess.check_output("docker ps --format '{{.Names}}'", shell=True).decode().splitlines()
            
            for c in containers:
                # Fuzzy match for docker compose names which might prepend folder name
                found = any(c in name for name in running_containers)
                if found:
                    log(f"Container '{c}' seems to be running.", "PASS")
                else:
                    log(f"Container '{c}' NOT found running.", "FAIL")
        else:
            log("Docker daemon is NOT running (or permission denied).", "FAIL")
    else:
        log("Docker is NOT installed or not in PATH.", "FAIL")

    # 2. Port Check
    ports = {
        "Postgres": 5432,
        "Redis": 6379,
        "Backend": 5000
    }
    for name, port in ports.items():
        if check_port("127.0.0.1", port):
            log(f"{name} port {port} is OPEN.", "PASS")
        else:
            log(f"{name} port {port} is CLOSED.", "FAIL")

    # 3. Backend Health Check
    if check_url("http://127.0.0.1:5000/api/db/health"):
        log("Backend DB Health check PASSED.", "PASS")
    else:
        log("Backend DB Health check FAILED.", "FAIL")

    # 4. PX4 Environment (Heuristic)
    # Check for PX4-Autopilot in common locations
    possible_px4_paths = [
        "../PX4-Autopilot",
        "../../PX4-Autopilot",
        os.path.expanduser("~/PX4-Autopilot"),
        "C:/PX4-Autopilot",
        "D:/PX4-Autopilot"
    ]
    px4_found = False
    for p in possible_px4_paths:
        if os.path.isdir(p):
            log(f"PX4-Autopilot found at: {p}", "PASS")
            px4_found = True
            break
    
    if not px4_found:
        log("PX4-Autopilot directory NOT found in common locations.", "WARN")

    # 5. Python Environment
    pkgs = ["mavsdk", "redis", "flask", "psycopg2"]
    for p in pkgs:
        # map package name to import name if different
        import_name = "redis" if p == "redis" else p
        import_name = "psycopg2" if p == "psycopg2" else import_name
        
        if check_package(import_name):
             log(f"Python package '{p}' is installed.", "PASS")
        else:
             log(f"Python package '{p}' is NOT installed.", "FAIL")

    log("Diagnosis Complete.")

if __name__ == "__main__":
    main()
