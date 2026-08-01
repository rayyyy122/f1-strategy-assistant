#!/bin/bash
# F1 策略助手 — VPS 一键部署脚本（Ubuntu 22.04 / 24.04）
#
# 用法:
#   sudo bash deploy/vps-setup.sh [cloudflared-token]
#
# 功能:
#   1. 安装 Python/venv/git 等系统依赖
#   2. 创建 venv 并安装 backend/requirements.txt
#   3. 创建 .env 模板（若不存在）
#   4. 注册并启动 systemd 服务 f1-backend（127.0.0.1:8000，仅隧道可访问）
#   5. 若提供 token：安装 cloudflared 并注册为系统服务（命名隧道副本）
#
# 之后还需手动做:
#   - 编辑 .env 填入真实 key（或直接从 Mac: scp .env root@VPS:<repo>/.env）
#   - systemctl restart f1-backend
#   - 从 Mac 迁移数据: rsync -avz data/ .fastf1_cache/ root@VPS:<repo>/

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="f1-backend"
TOKEN="${1:-}"

info() { echo -e "\033[1;34m[INFO]\033[0m $1"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m $1"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $1"; }

if [ "$EUID" -ne 0 ]; then
  echo "请用 sudo 运行: sudo bash deploy/vps-setup.sh [cloudflared-token]"
  exit 1
fi

# ---- 1. 系统依赖 ----
info "安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl
ok "系统依赖完成"

# ---- 2. Python 虚拟环境 ----
if [ ! -d "$REPO_DIR/venv" ]; then
  info "创建 Python 虚拟环境..."
  python3 -m venv "$REPO_DIR/venv"
fi
info "安装 Python 依赖（约 1-2 分钟）..."
"$REPO_DIR/venv/bin/pip" install -q --upgrade pip
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/backend/requirements.txt"
ok "Python 依赖完成"

# ---- 3. .env ----
if [ ! -f "$REPO_DIR/.env" ]; then
  warn ".env 不存在，创建模板（请编辑填入真实 key，然后 systemctl restart $SERVICE_NAME）"
  cat > "$REPO_DIR/.env" <<'EOF'
DEEPSEEK_API_KEY=
FRONTEND_API_KEY=o1c2iHuutraOhIHT5DyOMJaA39hTR6gG
EOF
  chmod 600 "$REPO_DIR/.env"
fi

# ---- 4. systemd 服务 ----
# 注意：必须单 worker（会话内存状态 memory_cache 在进程内），不要加 --workers
info "注册 systemd 服务: $SERVICE_NAME"
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=F1 Strategy Assistant Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=PYTHONPATH=$REPO_DIR
ExecStart=$REPO_DIR/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
# 内存保护：超过 1.5G 自动重启（fastf1 加载大数据时防 OOM 挂死）
MemoryMax=1.5G

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now $SERVICE_NAME
ok "后端服务已启动（127.0.0.1:8000，仅隧道可访问）"

# ---- 5. cloudflared（命名隧道副本，与 Mac 并行运行后再下掉 Mac 侧）----
if [ -n "$TOKEN" ]; then
  if ! command -v cloudflared >/dev/null 2>&1; then
    info "安装 cloudflared..."
    ARCH="$(dpkg --print-architecture)"
    curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
    dpkg -i /tmp/cloudflared.deb
    rm -f /tmp/cloudflared.deb
  fi
  info "注册命名隧道副本..."
  cloudflared service install "$TOKEN"
  ok "cloudflared 服务已启动"
else
  warn "未提供 cloudflared token，跳过隧道安装。稍后手动执行:"
  echo "  （token 在 Zero Trust 控制台 → Networks → Tunnels → 你的隧道 → Configure 页面复制）"
  echo "  curl -fsSL -o /tmp/cf.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i /tmp/cf.deb"
  echo "  cloudflared service install <TOKEN>"
fi

echo ""
ok "部署脚本执行完毕"
echo ""
echo "健康检查:  curl http://127.0.0.1:8000/api/health"
echo "查看日志:  journalctl -u $SERVICE_NAME -f"
