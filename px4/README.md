# PX4 Teacher Brain (SITL)

This folder outlines how to run PX4 SITL (Gazebo Harmonic) and collect teacher-driven demonstrations to train a student policy.

## Prereqs
- PX4-Autopilot installed (see `sentinel.config.json` paths if relevant)
- Gazebo Harmonic world with a multirotor
- QGroundControl for parameter changes
- Python (Windows or WSL) with `mavsdk`
- EKF2 GPS-denied config applied (see `../px4_config/gps_denied.params`)

## SITL Startup (WSL recommended)
```
# In WSL Ubuntu
git clone https://github.com/PX4/PX4-Autopilot
cd PX4-Autopilot
make px4_sitl gazebo
# SITL exposes MAVLink on UDP:14540 by default
```

## Teacher Demo Collection
Use `training/px4_teacher_collect.py` to connect to SITL and record demonstrations.
- Arms and takes off
- Runs a simple teacher (waypoint-follow + obstacle-aware yaw bias if range available)
- Logs telemetry and teacher actions to CSV

Run:
```
# Windows PowerShell (ensure Python has mavsdk installed)
Set-Location "D:\docs\lesnar\Lesnar AI"
& .\.venv\Scripts\python.exe .\training\px4_teacher_collect.py --system 127.0.0.1:14540 --out .\dataset\px4_teacher --duration 180 --hz 10
```

## Notes
- If you have rangefinder/obstacle sensors in Gazebo, the script biases yaw away from close obstacles.
- For GPS-denied validation, ensure EKF2 optical flow + rangefinder is active.
- Convert the CSV to your training format or adapt `train_navigation.py` to consume telemetry-based actions.
