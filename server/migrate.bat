@echo off
rem Creates the database (pos_db) and its tables, or updates them to the latest version.
rem Uses the login in server\.env. The service also does this by itself on every start.
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
.venv\Scripts\python -c "from app.migrate import migrate; migrate(); print('Database is up to date.')"
if errorlevel 1 (
    echo.
    echo Migration failed. Check DB_USER / DB_PASSWORD in server\.env and that MySQL is running.
)
pause
