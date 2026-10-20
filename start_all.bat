@echo off
rem Starts the Python service in its own window, waits until it answers, then starts the Vue web app.
cd /d "%~dp0"
start "POS Service" cmd /k "%~dp0start_server.bat"

echo Waiting for the POS service on http://localhost:8000 ...
:wait
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/api/health >nul 2>&1 || goto wait
echo Service is ready.

start "POS Web" cmd /k "%~dp0start_web.bat"
