@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/4] checking virtualenv ...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo Python not found. Install Python 3.10+ first.
        pause
        exit /b 1
    )
)

echo [2/4] installing dependencies ...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt

echo [3/4] seeding database ...
".venv\Scripts\python.exe" -X utf8 seed.py

echo [4/4] starting server at http://127.0.0.1:8000
start "" http://127.0.0.1:8000/docs
".venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
