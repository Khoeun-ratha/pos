@echo off
rem Starts the POS service on port 8000. Database settings come from server\.env (MySQL; see .env.example).
cd /d "%~dp0"
if not exist .venv (
    echo Creating Python environment...
    python -m venv .venv
)
.venv\Scripts\python -m pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
