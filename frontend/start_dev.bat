@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  BudaiAgentMesh 前端一键启动 (Windows, Astryx)
rem ============================================================

if not exist "node_modules" (
  echo [1/2] 安装前端依赖, 首次约 1-3 分钟...
  call npm install
  if errorlevel 1 (
    echo [错误] npm install 失败
    pause
    exit /b 1
  )
) else (
  echo [1/2] 依赖已安装
)

echo [2/2] 前端已就绪: http://localhost:5173  ^(需后端同时运行^)
echo.
call npm run dev

pause
