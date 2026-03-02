@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Activate AirSim Python env if present; fall back to system Python
set VENV_DIR=%~dp0..\airsim-env\Scripts
if exist "%VENV_DIR%\python.exe" (
    call "%VENV_DIR%\activate.bat"
)

echo Running GPU environment check...
python "%~dp0..\scripts\check_gpu_env.py"

echo.
echo Collecting a small validation dataset (optional)...
echo Press Ctrl+C to skip.
python "%~dp0..\training\collect_airsim_dataset.py" --split val --count 50 --move --sleep 0.1

echo.
echo Starting UNet training...
python "%~dp0..\training\train_unet.py" --data "%~dp0..\dataset" --img_size 256 256 --batch 4 --epochs 5 --classes 1 --out "%~dp0..\runs\unet" --fp16

if defined VENV_DIR (
    call "%VENV_DIR%\deactivate.bat" 2>nul
)
endlocal
