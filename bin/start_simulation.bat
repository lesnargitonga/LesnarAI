@echo off
echo Starting Lesnar AI Drone Simulation...
cd /d "%~dp0..\drone_simulation"
python main.py
cd ..
