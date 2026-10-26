# F1 策略助手 — 迁移完成状态

> 迁移方向：后端从另一台 MacBook 迁回**当前 Mac**（`/Users/ray/Desktop/f1-strategy-assistant`）。
> 完成时间：2026-10-27

---

## 最终架构

| 组件 | 位置 | 状态 |
|---|---|---|
| 前端 | Cloudflare Pages | 在线 |
| 后端 API | **当前 Mac** `127.0.0.1:8000` | 已运行（用户级 LaunchAgent） |
| cloudflared 隧道 | **当前 Mac** `com.cloudflare.cloudflared` | 已运行 |
| 公网域名 | `api.fi-strategy-assistant-website.website` | 指向当前 Mac |
| 另一台 MacBook | 后端 + cloudflared | 待停止 |

---

## 当前 Mac 服务配置

### 后端服务

- **类型**：用户级 `~/Library/LaunchAgents/f1-backend.plist`
- **运行用户**：`ray`
- **Python**：`~/.venvs/f1-strategy-assistant/bin/python`（Python 3.13）
- **启动命令**：
  ```bash
  /Users/ray/.venvs/f1-strategy-assistant/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
  ```
- **工作目录**：`/Users/ray/Desktop/f1-strategy-assistant`
- **环境变量**：`PYTHONPATH=/Users/ray/Desktop/f1-strategy-assistant`
- **日志**：
  - `~/Library/Logs/f1-backend.log`
  - `~/Library/Logs/f1-backend_error.log`

### cloudflared

- 已通过 `sudo cloudflared service install <TOKEN>` 注册为系统服务
- 使用同一 tunnel `f1-assistant`

---

## 常用运维命令

### 后端

```bash
# 查看状态
launchctl list | grep f1-backend

# 重启后端
launchctl unload ~/Library/LaunchAgents/f1-backend.plist
launchctl load -w ~/Library/LaunchAgents/f1-backend.plist
launchctl start f1-backend

# 查看日志
tail -f ~/Library/Logs/f1-backend_error.log

# 本地健康检查
curl http://127.0.0.1:8000/api/health
```

### cloudflared

```bash
# 停止
sudo launchctl stop com.cloudflare.cloudflared

# 启动
sudo launchctl start com.cloudflare.cloudflared

# 卸载重装
sudo cloudflared service uninstall
sudo cloudflared service install <TOKEN>
```

### 公网验证

```bash
curl https://api.fi-strategy-assistant-website.website/api/health
```

---

## 代码更新流程

在当前 Mac 改完代码后：

```bash
cd /Users/ray/Desktop/f1-strategy-assistant

# 如果依赖有变化
~/.venvs/f1-strategy-assistant/bin/pip install -r backend/requirements.txt

# 重启服务
launchctl unload ~/Library/LaunchAgents/f1-backend.plist
launchctl load -w ~/Library/LaunchAgents/f1-backend.plist
launchctl start f1-backend
```

如果改了前端，push 到 main 后 Cloudflare Pages 会自动部署。

---

## 注意事项

- **不要用 `/Library/LaunchDaemons`**：root 运行的系统服务对 `/Users/ray/Desktop` 下的文件有 TCC/SIP 访问限制，会导致 `PermissionError: Operation not permitted`。
- **服务专用 venv 在 `~/.venvs/`**：避开 Desktop 目录的权限/ provenance 属性问题。
- **项目内 `./venv/` 仍可用于本地开发**（已重建为 Python 3.13），`./run_backend.sh` 可正常使用。
- `backend/data/` 已加入 git；`.gitignore` 已修正为 `/data/`，不会再误忽略。
- 切换前需确保另一台 MacBook 的后端和 cloudflared 已停止，避免 Cloudflare 在多个 connector 之间随机路由。

---

## 待完成

- [ ] 停止另一台 MacBook 的后端和 cloudflared
- [ ] 停止后再次验证公网健康检查仍正常
- [ ] 可选：删除另一台 MacBook 上的项目副本
