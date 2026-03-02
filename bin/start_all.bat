@echo off
echo ======================================
echo Lesnar AI - Starting All Services
echo ======================================
echo.

echo Starting backend server...
start "Lesnar AI Backend" cmd /k "cd backend && python app.py"
timeout /t 3 /nobreak > nul

echo Starting frontend dashboard...
start "Lesnar AI Frontend" cmd /k "cd frontend && npm start"
timeout /t 3 /nobreak > nul

echo.
echo ======================================
echo All services started!
echo ======================================
echo.
echo Backend: http://localhost:5000
echo Frontend: http://localhost:3000
echo.
echo Press any key to exit...
pause > nul
