@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  BudaiAgentMesh backend launcher (Windows)
rem  Auto: find Python -> create venv -> install deps -> seed -> run
rem  NOTE: keep this file ASCII-only to avoid cmd codepage issues
rem ============================================================

rem ---------- 1. locate Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  if exist "D:\development\anaconda\python.exe" set "PY=D:\development\anaconda\python.exe"
)
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.12 and check "Add to PATH".
  pause
  exit /b 1
)

rem ---------- 2. create / repair venv ----------
if exist ".venv\Scripts\python.exe" goto venv_ok
if exist ".venv" (
  echo [INFO] Detected non-Windows .venv, rebuilding...
  rmdir /s /q ".venv"
)
echo [1/4] Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 (
  echo [ERROR] Failed to create venv
  pause
  exit /b 1
)

:venv_ok
echo [2/4] Installing dependencies...
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency install failed
  pause
  exit /b 1
)

rem ---------- 3. seed demo data (idempotent) ----------
echo [3/4] Initializing demo data...
.venv\Scripts\python -m scripts.seed_demo

rem ---------- 4. start ----------
echo.
echo [4/4] Backend ready:
echo    API docs: http://127.0.0.1:8000/docs
echo    Press Ctrl+C to stop
echo.
.venv\Scripts\python -m uvicorn app.main:app --port 8000

pause
