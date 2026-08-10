#!/usr/bin/env bash
# ============================================================
#  BudaiAgentMesh 一键启动 (macOS)
#
#  用法:
#    ./start_mac.sh                  # 后端 + 前端 全部启动
#    ./start_mac.sh --backend-only   # 只启后端
#    ./start_mac.sh --frontend-only  # 只启前端
#    ./start_mac.sh --no-seed        # 跳过演示数据 seed (已有数据时更快)
#
#  访问:
#    前端 http://localhost:5173       (账号: admin / admin123)
#    后端 http://127.0.0.1:8000/docs
#
#  停止: Ctrl+C  (自动清理前后端进程)
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$ROOT/.venv"

BACKEND_ONLY=0
FRONTEND_ONLY=0
NO_SEED=0
for arg in "$@"; do
  case "$arg" in
    --backend-only) BACKEND_ONLY=1 ;;
    --frontend-only) FRONTEND_ONLY=1 ;;
    --no-seed) NO_SEED=1 ;;
    *)
      echo "[ERROR] 未知参数: $arg"
      echo "  支持: --backend-only / --frontend-only / --no-seed"
      exit 1
      ;;
  esac
done

say() { printf '\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

echo "============================================================"
say "  BudaiAgentMesh 一键启动 (macOS)"
echo "============================================================"

# ---------- 0. 工具检查 ----------
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  fail "未检测到 Node.js/npm。请先安装 (推荐 Homebrew): brew install node"
fi
NODE_MAJOR="$(node -v | sed 's/^v//; s/\..*//')"
if [ "$NODE_MAJOR" -lt 18 ]; then
  fail "Node 版本过低 ($(node -v)), 需要 >= 18, 建议 20/22。请升级: brew upgrade node"
fi

# ---------- 1. Python 环境 (遵循项目约定: pyenv 优先 3.11) ----------
PYTHON=""
if command -v pyenv >/dev/null 2>&1; then
  cd "$ROOT"
  V3_11="$(pyenv versions --bare 2>/dev/null | sed 's/^[ *]*//' | grep -E '^3\.11\.' | sort -V | tail -1 || true)"
  if [ -n "$V3_11" ]; then
    pyenv local "$V3_11" >/dev/null 2>&1 || true   # 写入 .python-version (项目已是 3.11.9 则为无操作)
    say "  [1/6] Python: 使用 pyenv $V3_11"
  else
    V_ANY="$(pyenv versions --bare 2>/dev/null | sed 's/^[ *]*//' | grep -E '^3\.(9|1[0-9])\.' | sort -V | tail -1 || true)"
    if [ -n "$V_ANY" ]; then
      pyenv local "$V_ANY" >/dev/null 2>&1 || true
      warn "  [1/6] Python: pyenv 无 3.11, 使用 $V_ANY (建议: pyenv install 3.11.9)"
    else
      warn "  [1/6] Python: pyenv 未安装可用版本, 尝试系统 python3"
    fi
  fi
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PYTHON="python3"
  fi
else
  warn "  [1/6] Python: 未安装 pyenv (建议: brew install pyenv && pyenv install 3.11.9), 使用系统 python3"
  if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
  fi
fi
if [ -z "$PYTHON" ]; then
  fail "未检测到可用的 Python 3 (>= 3.10)。请安装: brew install python@3.11"
fi
say "  [1/6] Python: $("$PYTHON" --version)"

# ---------- 2. 虚拟环境 (Windows .venv 在 Mac 下需重建) ----------
say "  [2/6] 虚拟环境: $VENV"
if [ -f "$VENV/Scripts/python.exe" ]; then
  warn "      检测到 Windows 版 .venv, 正在删除并重建..."
  rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
VENV_PY="$VENV/bin/python"
"$VENV_PY" --version

# ---------- 3. 后端依赖 ----------
say "  [3/6] 安装后端依赖 (首次约 1-3 分钟)..."
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r "$BACKEND/requirements.txt" || fail "后端依赖安装失败, 请查看上方错误"

# ---------- 4. 演示数据 (幂等) ----------
mkdir -p "$BACKEND/data"
if [ "$NO_SEED" -eq 0 ]; then
  say "  [4/6] 初始化演示数据..."
  ( cd "$BACKEND" && "$VENV_PY" -m scripts.seed_demo ) || warn "      演示数据初始化失败(可忽略, 再次启动会自动重试)"
else
  warn "  [4/6] 跳过演示数据 (--no-seed)"
fi

# ---------- 5. 启动后端 ----------
BACKEND_PID=""
if [ "$FRONTEND_ONLY" -eq 0 ]; then
  if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    warn "  [5/6] 端口 8000 已被占用, 跳过启动后端 (如需重启请先停掉占用进程)"
  else
    say "  [5/6] 启动后端: http://127.0.0.1:8000/docs (日志: backend/uvicorn.log)"
    ( cd "$BACKEND" && exec "$VENV_PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 ) \
      > "$BACKEND/uvicorn.log" 2>&1 &
    BACKEND_PID=$!
  fi
fi

# ---------- 6. 启动前端 ----------
FRONTEND_PID=""
if [ "$BACKEND_ONLY" -eq 0 ]; then
  if [ ! -d "$FRONTEND/node_modules" ]; then
    say "  [6/6] 安装前端依赖 (首次约 1-3 分钟)..."
    ( cd "$FRONTEND" && npm install --no-audit --no-fund ) || fail "前端依赖安装失败"
  fi
  if lsof -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
    warn "  [6/6] 端口 5173 已被占用, 跳过启动前端 (如需重启请先停掉占用进程)"
  else
    say "  [6/6] 启动前端: http://localhost:5173 (日志: frontend/vite.log)"
    ( cd "$FRONTEND" && exec npm run dev ) > "$FRONTEND/vite.log" 2>&1 &
    FRONTEND_PID=$!
  fi
fi

# ---------- 汇总 ----------
echo ""
echo "============================================================"
say "  启动完成! 按 Ctrl+C 同时停止前后端"
echo "============================================================"
[ -n "$BACKEND_PID" ] && echo "  后端: http://127.0.0.1:8000/docs   (PID $BACKEND_PID, 日志 backend/uvicorn.log)"
[ -n "$FRONTEND_PID" ] && echo "  前端: http://localhost:5173       (PID $FRONTEND_PID, 日志 frontend/vite.log)"
[ "$FRONTEND_ONLY" -eq 1 ] && echo "  后端未启动 (--frontend-only)"
[ "$BACKEND_ONLY" -eq 1 ] && echo "  前端未启动 (--backend-only)"
echo "  登录账号: admin / admin123"
echo ""

# ---------- 等待并统一清理 ----------
cleanup() {
  echo ""
  warn "  正在停止服务..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  # 兜底: 清理本脚本派生的残留进程
  jobs -pr | xargs -r kill 2>/dev/null || true
  say "  已停止, 再见!"
}
trap cleanup EXIT INT TERM

# 任一进程退出则整体退出 (后端挂 = 前端也没意义; 前端挂 = 一并退出)
while true; do
  if [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    warn "  后端进程已退出, 查看日志: backend/uvicorn.log"
    break
  fi
  if [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    warn "  前端进程已退出, 查看日志: frontend/vite.log"
    break
  fi
  sleep 2
done
