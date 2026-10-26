---
name: f1-strategy-assistant
description: F1 策略助手项目上下文沉淀。当用户在该项目中提问、修改代码、调试 bug，或提到 F1 策略助手、race_context Agent、orchestrator、ChatWindow、session_store 等本项目特定术语时，必须使用此 skill 加载项目背景，避免重新探索。
type: prompt
whenToUse: 在 F1 策略助手项目（/Users/taodingrui/Desktop/Agent）中处理任何任务时自动加载，包括代码修改、调试、架构决策、新功能实现、部署运维、恢复进度。
---

# F1 策略助手 — 项目上下文

## 项目定位

多 Agent 对话式 F1 策略分析助手。前端是 ChatGPT/Claude.ai 风格的对话框，后端用 4 个 LLM Agent 协作分析 F1 比赛策略。已能用，仍在迭代防幻觉、可视化、UX。

## 技术栈

| 层 | 选择 |
|---|---|
| 后端 | Python 3.13 + FastAPI + uvicorn + OpenAI SDK + DeepSeek API |
| Agent | 自研 BaseAgent + tool calling，**不用** LangChain / Anthropic SDK |
| 数据 | FastF1 (历史)、OpenF1 (天气)、Jolpica (排位赛) |
| 存储 | JSON 文件（sessions / traces）+ FastF1 cache |
| 前端 | React 18 + Vite + Tailwind v4 + lucide-react + react-markdown |
| LLM 模型 | `deepseek-chat`（默认）+ `deepseek-reasoner`（可切换有 reasoning_content） |
| 部署 | Cloudflare 命名 Tunnel（固定域名）+ cloudflared service（后台常驻） |

## 环境变量（.env）

```bash
DEEPSEEK_API_KEY=sk-xxx                    # 必需；同时驱动 LLM 调用和 Search/Fetch API
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
FRONTEND_API_KEY=xxx                       # 前端访问后端的 X-API-Key（可选，不设置则不校验）
BRAVE_SEARCH_API_KEY=xxx                   # Brave 搜索 API（可选；DeepSeek 搜索失败时的次级后备）
LOG_LEVEL=INFO
```

## 公网部署

- 前端：`https://fi-strategy-assistant-website.website`（Cloudflare Pages）
- 后端：`https://api.fi-strategy-assistant-website.website`（Cloudflare 命名 Tunnel `f1-assistant`）

Tunnel token 位置：**Cloudflare Dashboard → Zero Trust → Networks → Tunnels → f1-assistant → Configure → Token**

macOS 上启动/停止/重装 cloudflared：

```bash
sudo cloudflared service install <TOKEN>
sudo launchctl start com.cloudflare.cloudflared
sudo launchctl stop com.cloudflare.cloudflared
```

## 关键文件地图

```
backend/
├── main.py                        # FastAPI 入口 + SSE + sessions API
├── config.py                      # 环境变量、路径
├── agents/
│   ├── base.py                    # BaseAgent 核心循环（tool use + streaming）
│   ├── race_context.py            # 赛道+天气+历史
│   ├── tire_strategist.py         # 轮胎退化分析
│   ├── competitor_analyst.py      # 对手分析
│   ├── synthesis.py               # 汇总
│   └── intake.py                  # 赛前追问补全车队/车手/轮次
├── tools/
│   ├── registry.py                # ToolRegistry 全局单例
│   ├── circuit_tools.py           # 25 条赛道知识库 + 别名表 + found 标志
│   ├── tire_tools.py / session_tools.py / weather_tools.py / strategy_tools.py
│   └── web_tools.py               # DeepSeek Search API 优先 + Wiki/DDG/Bing 级联兜底 + fetch_page
├── harness/
│   ├── orchestrator.py            # handle_prompt + mode 分发
│   ├── router.py                  # Intent 关键词 + LLM 双层路由
│   ├── logger.py                  # 双写 stdout+文件，含 token_tracker
│   └── guardrails.py
└── memory/
    ├── session_store.py           # JSON 文件持久化
    ├── manager.py                 # ShortTerm + WorkingMemory
    └── trace_store.py             # RL 轨迹

frontend/src/
├── App.tsx                        # Sidebar + 主区域
├── components/
│   ├── ChatWindow.tsx             # 主对话容器，SSE 事件分发
│   ├── MessageBubble.tsx          # Markdown + Copy + 折叠 thinking + tool activity
│   └── AgentThinkingBlock.tsx
├── hooks/useSSE.ts
└── utils/api.ts + f1Theme.ts
```

## 模式

| mode | 触发 | 流程 |
|---|---|---|
| `pre_race` | "分析 X 站策略" | 加载数据 → race_context → tire+competitor 并行 → synthesis → strategy_card |
| `post_race` | "复盘 X 站" | 赛历解析比赛 → 加载实际结果 → comparison_card → synthesis 文字总结 |
| `track_info` | "介绍 X 赛道" | 单跑 race_context（force_tool=True） |
| `quick_question` | "什么是 DRS" | 单跑 race_context（force_tool=False） |
| `follow_up` | "如果安全车呢" | 仅 synthesis，复用 working memory |
| `off_topic` | "红烧肉怎么做" | 路由层短路，固定话术拒答 |

## 已踩过的坑（别再犯）

- `asyncio.Queue.put_nowait` 在 `to_thread` 工作线程里不安全 → 用 `loop.call_soon_threadsafe`（`agents/base.py`）。
- `_drain_with` 的 producer task 异常被静默吞掉 → producer 存 exception，主循环看到 END_SENTINEL 后 raise（`harness/orchestrator.py`）。
- `session_meta` 触发 sessionId 变化 → `knownSessionIdRef` 同步标记，跳过 prop 引发的 useEffect 重载（`ChatWindow.tsx`）。
- Agent 拿不到工具数据时**幻觉** → 工具返回 `{"found": false}` + IRON RULE prompt + `tool_choice="required"` 强制首轮。
- `force_first_tool_call` 设为 config 全局 → 改成 per-call 参数，由 orchestrator 按 mode 传入（`base.py` + `orchestrator.py`）。
- 赛历逐年变化，不要硬编码轮次 → post_race 四级解析阶梯，轮次永远查当年赛历（`orchestrator.py:_run_post_race`）。
- 无关问题白烧 token → router 加 `off_topic` mode，orchestrator 短路固定话术（`router.py` + `orchestrator.py`）。
- intake 反问回填后循环问同一字段 → `_extract_fields_from_prompt` 代码级兜底，已确认字段不覆盖（`orchestrator.py` + `agents/intake.py`）。
- 免费搜索 SDK 在本网络不可靠 → DeepSeek Search/Fetch API 为首选源，Wiki/DDG/Bing 级联兜底（`tools/web_tools.py`）。
- quick_question 徽章误标"赛道分析师" → `agent_start` 事件加 `label` 字段做展示层覆盖（`orchestrator.py` + `MessageBubble.tsx`）。
- FastF1 `int(NaN)` 报错 → 改用 `session.results` 官方分类 + `_safe_int/_safe_float`（`tools/strategy_tools.py`）。
- uvicorn `--reload` 子进程缺 PYTHONPATH → `run_backend.sh` 显式 export PYTHONPATH。
- 免费 tunnel 域名随机变化 → Cloudflare 命名 Tunnel + launchd service 常驻。

## 常用命令

```bash
# 一键启动本地前后端
./run_all.sh

# 或手动
./run_backend.sh
cd frontend && npm run dev

# 验证后端 import
PYTHONPATH=$(pwd) ./venv/bin/python -c "from backend.main import app"

# 看日志
tail -80 logs/backend_$(date +%Y%m%d).log

# 公网健康检查
curl https://api.fi-strategy-assistant-website.website/api/health
curl https://fi-strategy-assistant-website.website

# 重启 cloudflared
sudo launchctl stop com.cloudflare.cloudflared
sudo launchctl start com.cloudflare.cloudflared
```

## 添加新东西的套路

- **新工具**：在 `backend/tools/<name>_tools.py` 写 async 函数 → `registry.register(...)` → 在 agents 列表里指定谁能用。
- **新 Agent**：复制 `agents/race_context.py` → 改 SYSTEM_PROMPT 和 tools → 在 `orchestrator.py:AGENT_FACTORIES` 注册 → 编排里调用。
- **新 mode**：在 `harness/router.py` 加描述 → `orchestrator.py:handle_prompt` 加分支 → 写 `_run_<mode>`。
- **前端新 SSE 事件**：在 `types/index.ts:SSEEvent` 加 member → `ChatWindow.tsx:handleEvent` 加 case → 必要时加 `MessageBubble` 渲染。

## 设计哲学

- **Iron Rule prompt + `tool_choice="required"` 双重保险**：单靠 prompt 防不住幻觉。
- **流式优先**：SSE 全程流式，前端实时呈现 thinking / text / tool / 卡片。
- **结构化输出**：Agent 间用 JSON 通信，用户面用 Markdown。
- **手写 agent 循环**：故意不用 LangChain，方便加 RL hook。
