#!/bin/bash
# F1 策略助手 — 一键启动脚本
# 启动：后端 + 前端
# 使用 Cloudflare 命名 Tunnel（固定域名），无需每次启动 tunnel
# 按 Ctrl+C 停止所有服务

cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

LOG_DIR="$PWD/logs"
mkdir -p "$LOG_DIR"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

# 清理函数：杀掉所有子进程
cleanup() {
    echo ""
    info "正在停止所有服务..."
    jobs -p | xargs kill -9 2>/dev/null
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    lsof -ti:5173 | xargs kill -9 2>/dev/null
    ok "所有服务已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

# 检查端口占用
if lsof -ti:8000 >/dev/null 2>&1; then
    warn "端口 8000 被占用，正在清理..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 1
fi
if lsof -ti:5173 >/dev/null 2>&1; then
    warn "端口 5173 被占用，正在清理..."
    lsof -ti:5173 | xargs kill -9 2>/dev/null
    sleep 1
fi

echo ""
echo "=========================================="
echo "  F1 策略助手 — 一键启动"
echo "=========================================="
echo ""

# ---- 配置前端环境变量（本地开发直连本地后端）----
info "配置前端环境变量..."
echo "VITE_API_URL=http://localhost:8000/api" > frontend/.env
ok "frontend/.env 已更新（本地开发）"

# ---- 启动后端 ----
info "启动后端 (localhost:8000)..."
./venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --log-level info \
    > "$LOG_DIR/backend_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
BACKEND_PID=$!
sleep 5

if ! lsof -ti:8000 >/dev/null 2>&1; then
    err "后端启动失败，查看日志: $LOG_DIR/backend_*.log"
    exit 1
fi
ok "后端已启动 (PID: $BACKEND_PID)"

# ---- 启动前端 ----
info "启动前端 (localhost:5173)..."
cd frontend
npm run dev > "$LOG_DIR/frontend_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
FRONTEND_PID=$!
cd ..
sleep 5

if ! lsof -ti:5173 >/dev/null 2>&1; then
    err "前端启动失败，查看日志: $LOG_DIR/frontend_*.log"
    kill -9 $BACKEND_PID 2>/dev/null
    exit 1
fi
ok "前端已启动 (PID: $FRONTEND_PID)"

echo ""
echo "=========================================="
echo "  服务状态"
echo "=========================================="
echo ""
ok "后端本地:  http://localhost:8000"
ok "前端本地:  http://localhost:5173"
echo ""
ok "后端公网:  https://api.fi-strategy-assistant-website.website (Cloudflare 命名隧道)"
echo ""
echo "前端公网由 Cloudflare Pages 托管（push 到 main 自动部署）:"
echo "  https://fi-strategy-assistant-website.website"
echo ""
echo "=========================================="
echo "  重要提示"
echo "=========================================="
echo ""
echo "1. 本脚本用于本地开发；前端线上由 Cloudflare Pages 自动部署"
echo "2. 后端公网走 Cloudflare 命名 Tunnel，确保 cloudflared 服务在运行"
echo "3. 按 Ctrl+C 停止所有服务"
echo ""

# 保持脚本运行，等待用户中断
wait
