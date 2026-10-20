@echo off
rem Web app (Vue) at http://localhost:8080 - start the service first (start_server.bat).
rem While changing the code, use "npm run dev" in the web folder instead (reloads on save).
cd /d "%~dp0web"
if not exist node_modules (
    echo Installing web packages...
    call npm install
)
echo Building the web app...
call npm run build || (pause & exit /b 1)
start "" http://localhost:8080
call npx vite preview
