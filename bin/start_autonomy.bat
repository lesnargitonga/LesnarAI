@echo off
setlocal EnableDelayedExpansion

set ROOT=%~dp0..\
set AIRSIM_DIR=%ROOT%airsim\
set SCRIPT=%AIRSIM_DIR%autonomy_controller.py

REM Choose Python interpreter: prefer local venv, else fall back to py launcher
set PYTHON_EXE=
if exist "%ROOT%airsim-env\Scripts\python.exe" (
  set "PYTHON_EXE=%ROOT%airsim-env\Scripts\python.exe"
) else (
  for %%I in (py.exe) do (
    if not "%%~$PATH:I"=="" set PYTHON_EXE=py -3
  )
  if "%PYTHON_EXE%"=="" set PYTHON_EXE=python
)

echo [INFO] Using Python: %PYTHON_EXE%
echo [INFO] Working dir : %AIRSIM_DIR%
echo [INFO] Script      : %SCRIPT%

if not exist "%SCRIPT%" (
  echo [ERROR] Script not found: %SCRIPT%
  exit /b 1
)

pushd "%AIRSIM_DIR%"
"%PYTHON_EXE%" -u "%SCRIPT%"
set EXITCODE=%ERRORLEVEL%
popd

if not %EXITCODE%==0 (
  echo [ERROR] Autonomy controller exited with code %EXITCODE%
)

endlocal & exit /b %EXITCODE%
