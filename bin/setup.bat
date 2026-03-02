@echo off
echo ======================================
echo Lesnar AI Drone Automation System
echo ======================================
echo.

setlocal
set ROOT=%~dp0..\

echo [1/3] Setting up backend Python venv...
if not exist "%ROOT%backend-env\Scripts\python.exe" (
	python -m venv "%ROOT%backend-env"
)
"%ROOT%backend-env\Scripts\python.exe" -m pip install --upgrade pip
"%ROOT%backend-env\Scripts\python.exe" -m pip install -r "%ROOT%backend\requirements.txt"

echo.
echo [2/3] Setting up AirSim/autonomy Python venv...
if exist "%ROOT%airsim\requirements.txt" (
	if not exist "%ROOT%airsim-env\Scripts\python.exe" (
		python -m venv "%ROOT%airsim-env"
	)
	"%ROOT%airsim-env\Scripts\python.exe" -m pip install --upgrade pip
	"%ROOT%airsim-env\Scripts\python.exe" -m pip install -r "%ROOT%airsim\requirements.txt"
) else (
	echo [INFO] No airsim\requirements.txt found; skipping autonomy venv install.
)

echo.
echo [3/3] Installing frontend dependencies...
cd /d "%ROOT%frontend"
call npm install
cd /d "%ROOT%"

echo.
echo ======================================
echo Setup Complete!
echo ======================================
echo.
echo To start everything (recommended):
echo   powershell -ExecutionPolicy Bypass -File .\start_everything.ps1
echo.
pause

endlocal
