@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem  BudaiAgentMesh 后端一键启动 (Windows)
rem  自动完成: 定位 Python -> 创建 venv -> 安装依赖 -> 种子数据 -> 启动
rem ============================================================

rem ---------- 1. 定位 Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  if exist "D:\development\anaconda\python.exe" set "PY=D:\development\anaconda\python.exe"
)
if not defined PY (
  echo [错误] 未找到 Python。请安装 Python 3.12 并勾选 "Add to PATH"。
  pause
  exit /b 1
)

rem ---------- 2. 创建/修复 venv ----------
if exist ".venv\Scripts\python.exe" goto venv_ok
if exist ".venv" (
  echo [提示] 检测到非 Windows 的 .venv ^(如 WSL 创建的^), 正在重建...
  rmdir /s /q ".venv"
)
echo [1/4] 创建虚拟环境...
%PY% -m venv .venv
if errorlevel 1 (
  echo [错误] 创建 venv 失败
  pause
  exit /b 1
)

:venv_ok
echo [2/4] 安装依赖...
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)

rem ---------- 3. 种子数据 ----------
echo [3/4] 初始化演示数据...
if not exist "data\budai_mesh.db" (
  .venv\Scripts\python -m scripts.seed_demo
) else (
  echo  已存在本地库, 跳过种子数据
)

rem ---------- 4. 启动 ----------
echo.
echo [4/4] 后端已就绪:
echo    API 文档: http://127.0.0.1:8000/docs
echo    按 Ctrl+C 停止
echo.
.venv\Scripts\python -m uvicorn app.main:app --port 8000

pause
