@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  BudaiAgentMesh frontend launcher (Windows, Astryx)
rem ============================================================

if not exist "node_modules" (
  echo [1/2] Installing frontend dependencies, first run takes 1-3 min...
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
  )
) else (
  echo [1/2] Dependencies already installed
)

echo [2/2] Frontend ready: http://localhost:5173  (backend must be running)
echo.
call npm run dev

pause
