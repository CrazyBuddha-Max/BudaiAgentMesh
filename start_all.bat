@echo off
rem ============================================================
rem  BudaiAgentMesh: launch backend and frontend in two windows
rem ============================================================
start "BudaiMesh-Backend" cmd /k "cd /d %~dp0backend && start_dev.bat"
start "BudaiMesh-Frontend" cmd /k "cd /d %~dp0frontend && start_dev.bat"
echo Launched. Wait for both windows:
echo   Frontend http://localhost:5173  (login: admin/admin123)
echo   Backend  http://127.0.0.1:8000/docs
