# F1 策略助手

面向 F1 方程式赛车的多 Agent 策略助手，对话框式交互。支持赛前策略分析、赛后复盘对比、快速问答与多轮追问。

## 本地开发

```bash
# 后端（FastAPI，localhost:8000）
./run_backend.sh

# 前端（Vite dev，localhost:5173）
cd frontend && npm run dev
```

或一键启动本地前后端：`./run_all.sh`

## 线上部署

- **前端 — Cloudflare Pages**：连接本仓库，push 到 `main` 自动构建部署
  - Build command: `cd frontend && npm install && npm run build`
  - Build output: `frontend/dist`
  - 域名: <https://fi-strategy-assistant-website.website>
  - 生产 API 地址按 `import.meta.env.PROD` 在 `frontend/src/utils/api.ts` 中注入，无需控制台额外配置
- **后端 — 本机 + Cloudflare 命名 Tunnel**：`./run_all.sh`（或 `run_backend.sh`）启动后，经 cloudflared 系统服务暴露为 <https://api.fi-strategy-assistant-website.website>
  - 后端 API 变更需要在本机重启服务才会生效，不会自动部署

## 架构

- `backend/` — FastAPI + 多 Agent 编排（Router → 数据加载 → 并行 Agent → Synthesis），SSE 流式输出
- `frontend/` — React + Vite + Tailwind，对话框 UI
- 详见 `IMPLEMENTATION_PLAN.md` 与 `FRONTEND_UPGRADE_PROGRESS.md`
