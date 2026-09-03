@echo off
setlocal
cd /d "%~dp0"
title Grad Prep Agent

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] First run: creating virtual environment...
    python -m venv .venv || goto :err
)

set MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

".venv\Scripts\python.exe" -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo [2/3] Installing core dependencies with CN mirror...
    ".venv\Scripts\python.exe" -m pip install -U pip -q -i %MIRROR% --timeout 300
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i %MIRROR% --timeout 300 --retries 5 || goto :err
)

echo [3/3] Starting server: http://127.0.0.1:8000
".venv\Scripts\python.exe" run.py
goto :eof

:err
echo.
echo ERROR: dependency install failed. Run setup_env.ps1 for retry with mirror fallback.
pause
