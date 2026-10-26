# F1 策略助手 — 后端迁移状态清单

> 迁移目标：把生产后端从当前 Mac 迁到另一台常驻开机的 MacBook，让当前 Mac 可以休眠/关机。
> 创建时间：2026-10-27

---

## 当前架构状态

| 组件 | 位置 | 状态 |
|---|---|---|
| 前端 | Cloudflare Pages | 在线，无需迁移 |
| 后端 API | 当前 Mac `localhost:8000` | 运行中，待切换 |
| cloudflared 隧道 | 当前 Mac `com.cloudflare.cloudflared` | 运行中，待停止 |
| 公网域名 | `api.fi-strategy-assistant-website.website` | 仍指向当前 Mac |

---

## 已完成（当前 Mac）

- [x] 代码已 push 到 GitHub（最新 `2b77f7e`）
- [x] Kimi Code 项目 skill 已创建并 push（`.kimi-code/skills/f1-strategy-assistant/SKILL.md`）
- [x] `.env` 已通过 SCP 复制到另一台 MacBook
- [x] 另一台 MacBook 已 `git clone` 项目

---

## 剩余步骤（另一台 MacBook）

### 1. 同步最新代码

```bash
cd ~/f1-strategy-assistant
git pull origin main
```

如果 HTTPS 失败：

```bash
# 在当前 Mac 上执行
scp -r /Users/taodingrui/Desktop/Agent/.kimi-code \
  <另一台Mac用户名>@<另一台Mac_IP>:~/f1-strategy-assistant/
```

### 2. 安装 Python 依赖

```bash
cd ~/f1-strategy-assistant
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3. 手动测试后端

```bash
source venv/bin/activate
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

新终端验证：

```bash
curl http://127.0.0.1:8000/api/health
```

正常后 `Ctrl+C` 停止手动进程。

### 4. 注册后端为 launchd 服务

创建启动脚本：

```bash
cat > ~/f1-strategy-assistant/run_service.sh <<'EOF'
#!/bin/bash
cd ~/f1-strategy-assistant
source venv/bin/activate
exec uvicorn backend.main:app --host 127.0.0.1 --port 8000
EOF
chmod +x ~/f1-strategy-assistant/run_service.sh
```

创建服务（替换 `<用户名>`）：

```bash
sudo tee /Library/LaunchDaemons/f1-backend.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>f1-backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/<用户名>/f1-strategy-assistant/run_service.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/<用户名>/f1-strategy-assistant/logs/backend_service.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/<用户名>/f1-strategy-assistant/logs/backend_service_error.log</string>
</dict>
</plist>
EOF

sudo launchctl load -w /Library/LaunchDaemons/f1-backend.plist
```

### 5. 安装并启动 cloudflared

```bash
brew install cloudflared
sudo cloudflared service install <CLOUDFLARED_TOKEN>
```

Token 来源：Cloudflare Dashboard → Zero Trust → Networks → Tunnels → f1-assistant → Configure → Token

### 6. 验证公网

```bash
curl https://api.fi-strategy-assistant-website.website/api/health
```

### 7. 切换：停止当前 Mac 的隧道

在**当前 Mac** 上执行：

```bash
sudo launchctl unload /Library/LaunchDaemons/com.cloudflare.cloudflared.plist
sudo launchctl remove com.cloudflare.cloudflared
```

---

## 切换后验证清单

- [ ] 新机器 `curl http://127.0.0.1:8000/api/health` 正常
- [ ] 公网 `curl https://api.fi-strategy-assistant-website.website/api/health` 正常
- [ ] 网站前端能正常对话
- [ ] 当前 Mac 休眠/关机后，网站仍可用

---

## 回滚方案

如果新机器出问题，重新在当前 Mac 启动隧道：

```bash
sudo cloudflared service install <CLOUDFLARED_TOKEN>
```

流量会重新指回当前 Mac。

---

## 后续代码更新

以后在当前 Mac 改完代码 push 后，在新机器上：

```bash
cd ~/f1-strategy-assistant
git pull origin main
source venv/bin/activate
pip install -r backend/requirements.txt  # 如果依赖有变化
sudo launchctl stop f1-backend
sudo launchctl start f1-backend
```
