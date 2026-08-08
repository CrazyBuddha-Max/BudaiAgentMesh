@echo off
chcp 65001 >nul 2>nul
rem ============================================================
rem  BudaiAgentMesh: restart backend in THIS window (no new windows)
rem  用法: 双击运行, 或在自己的后端窗口执行本脚本
rem ============================================================
title BudaiMesh-Backend
cd /d "%~dp0backend"

echo [1/2] Stopping old backend on :8000 ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /PID %%p /F >nul 2>nul
)
timeout /t 1 /nobreak >nul

echo [2/2] Starting backend (new code) ...
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
