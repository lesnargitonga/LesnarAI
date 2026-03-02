@echo off
echo Starting Lesnar AI Backend Server...
setlocal
set ROOT=%~dp0..\
set PY=%ROOT%backend-env\Scripts\python.exe

:: ENABLE REAL AIRSIM CONNECTION
set LESNAR_USE_AIRSIM=1

if exist "%PY%" (
	cd /d "%ROOT%backend"
	"%PY%" app.py
) else (
	echo [WARN] backend-env not found. Run setup.bat first.
	cd /d "%ROOT%backend"
	python app.py
)

endlocal
