@echo off
echo Starting Lesnar AI "Genius" RL Training...
echo This will train a new Brain with the upgraded Navigation Logic.

REM Use the virtual environment Python explicitly
REM This fixes the "ModuleNotFoundError: sb3_contrib" and usually the NumPy version issues
set "PYTHON_EXE=%~dp0..\airsim-env\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Error: Virtual environment not found at %PYTHON_EXE%
    echo Please ensure you have run the setup script.
    pause
    exit /b 1
)

cd /d "%~dp0..\rl"
"%PYTHON_EXE%" train_ppo.py --outdir "%~dp0..\runs\lesnar_phase1_episodic" --timesteps 1000000 %*


pause