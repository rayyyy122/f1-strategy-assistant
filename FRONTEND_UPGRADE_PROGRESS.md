# 前端现代化升级 — 进度跟踪

参考 ChatGPT / Claude.ai 风格的现代 LLM chat UI 改造。分 6 个步骤，逐步推进。

---

## 步骤总览

| # | 步骤 | 涉及范围 | 状态 |
|---|------|---------|------|
| 1 | 后端会话持久化（Tier 6） | `backend/memory/`, `backend/main.py` | ✅ 已完成 |
| 2 | 前端 Sidebar + 会话切换（Tier 1） | `frontend/src/components/`, `App.tsx` | ✅ 已完成 |
| 3 | Markdown 渲染 + Copy 按钮（Tier 2） | `MessageBubble.tsx` | ✅ 已完成 |
| 4 | 多行输入 + 停止生成 + 空状态（Tier 3） | `ChatWindow.tsx` | ✅ 已完成 |
| 5 | 体验细节（Tier 4） | 流式 markdown / 回到底部 / 重生 | ✅ 已完成 |
| 6 | F1 视觉化（Tier 5） | 配色 / 轮胎徽章 / 赛道缩略图 | ✅ 已完成 |

图例：⬜ 未开始 · 🔄 进行中 · ✅ 已完成

---

## 步骤 1: 后端会话持久化（Tier 6）

**目标**：将当前内存中的 `sessions: dict` 改为基于文件的持久化存储，支持列表/查询/删除。

**改动文件**：
- `backend/memory/session_store.py`（新建）— SessionStore 类，JSON 文件持久化
- `backend/memory/manager.py` — 与 SessionStore 集成
- `backend/main.py` — 新增 4 个 API 端点
- `backend/harness/orchestrator.py` — 调用 SessionStore 追加消息

**新增 API**：
- `GET /api/sessions` — 列出所有会话（id, title, created_at, message_count）
- `GET /api/sessions/{id}` — 返回某会话的完整消息历史
- `DELETE /api/sessions/{id}` — 删除会话
- `POST /api/chat` — 增加自动创建会话和标题（从首句生成）

**会话数据格式**（`data/sessions/{session_id}.json`）：
```json
{
  "id": "sess_abc123",
  "title": "2024 摩纳哥大奖赛策略",
  "created_at": "2026-05-26T20:00:00",
  "updated_at": "2026-05-26T20:05:00",
  "messages": [
    {"role": "user", "content": "...", "timestamp": "..."},
    {"role": "assistant", "content": "...", "agent": "synthesis", "timestamp": "..."}
  ]
}
```

**进度记录**：✅ 完成于 2026-05-26

实际改动：
- ✅ 新建 `backend/memory/session_store.py` — JSON 文件持久化（每会话一个文件）
- ✅ 修改 `backend/main.py` — 新增 5 个端点
  - `GET /api/sessions` — 列出所有会话（按更新时间倒序）
  - `GET /api/sessions/{id}` — 获取完整消息历史
  - `POST /api/sessions` — 显式创建（可选）
  - `DELETE /api/sessions/{id}` — 删除
  - `PATCH /api/sessions/{id}` — 更新标题
- ✅ `POST /api/chat` 升级
  - 自动创建会话（如未提供 session_id 或 ID 不存在）
  - 流式开头发送 `session_meta` 事件，告知前端 session_id
  - 自动持久化用户消息和 assistant 响应（含 strategy/comparison/data_cards）
  - 首条用户消息自动生成标题（截取前 40 字符）
- ✅ 测试通过：CRUD 端点全部正常工作

会话文件示例：`data/sessions/sess_xxxxxxxxxxxx.json`

存储位置：`/Users/taodingrui/Desktop/Agent/data/sessions/`

---

**目标**：左侧 Sidebar 显示会话列表，支持新建/切换/删除。

**改动文件**：
- `frontend/src/components/Sidebar.tsx`（新建）
- `frontend/src/components/ChatWindow.tsx` — 接收 `sessionId` 参数
- `frontend/src/App.tsx` — Sidebar + 主区域布局
- `frontend/src/utils/api.ts` — 新增 sessions API 封装
- `frontend/src/types/index.ts` — Session 类型

**布局**：
```
┌────────────┬─────────────────────┐
│ + 新对话   │  顶部栏              │
│ ─────────  ├─────────────────────┤
│ 摩纳哥...  │                     │
│ 银石...    │  消息区域            │
│ 已选中     │                     │
│            ├─────────────────────┤
│            │  输入框              │
└────────────┴─────────────────────┘
```

**进度记录**：✅ 完成于 2026-05-26

实际改动：
- ✅ `frontend/src/types/index.ts` — 新增 `SessionSummary`, `SessionDetail`, `StoredMessage` 类型；SSEEvent 增加 `session_meta`
- ✅ `frontend/src/utils/api.ts` — 新增 `listSessions`/`getSession`/`deleteSession`/`updateSessionTitle`
- ✅ `frontend/src/components/Sidebar.tsx` — 新建
  - 会话列表（按更新时间倒序，悬停显示删除按钮）
  - "+ 新对话" 按钮
  - 折叠按钮（折叠成 48px 窄条，只显示图标）
  - 加载中 / 空状态
  - 当前会话高亮
- ✅ `frontend/src/components/ChatWindow.tsx` — 重构
  - 接受 `sessionId` 和 `onSessionCreated` props
  - 切换 sessionId 时自动加载历史消息
  - 处理 `session_meta` 事件捕获新会话 ID
  - 把后端 `StoredMessage` 还原为前端 ChatMessage 列表（拆分 dataCard / strategy / comparison）
- ✅ `frontend/src/App.tsx` — Sidebar + 主区域布局
- ✅ `npm run build` 通过，0 类型错误

体验：
- 启动后无选中会话，显示空状态
- 输入并发送 → 后端自动创建会话 → SSE 流首发 `session_meta` → 前端记下 ID，sidebar 刷新
- 点击 sidebar 中的历史会话 → 加载完整消息 → 可继续追问

已知限制（留待 Step 5 polish）：
- Sidebar 只在新建会话时刷新，已有会话的标题/时间不会实时更新
- 删除会话用浏览器原生 confirm（应改为 UI 模态框）

---

**目标**：Agent 输出渲染为 Markdown（粗体、列表、表格），消息悬停显示 Copy 按钮。

**改动文件**：
- `frontend/package.json` — 添加 `react-markdown`, `remark-gfm`, `lucide-react`
- `frontend/src/components/MessageBubble.tsx` — 集成 Markdown 渲染 + Copy

**进度记录**：✅ 完成于 2026-05-26

实际改动：
- ✅ `npm install react-markdown remark-gfm lucide-react`（+ 1853 modules）
- ✅ `MessageBubble.tsx` 重写
  - `<MarkdownContent>` 子组件：用 `react-markdown` + `remark-gfm`
  - 自定义渲染器：p/strong/em/ul/ol/h1-h3/code/pre/blockquote/table/hr/a
  - 行内代码 `bg-zinc-800 + text-amber-300`
  - 代码块 `bg-zinc-950 + 边框 + 横向滚动`
  - 表格带边框 + 头部底色
  - 链接琥珀色 + 下划线
- ✅ `<AgentBadge>` 子组件：每个 Agent 有独立的图标 + 颜色
  - race_context: 🏁 灰
  - tire_strategist: 🛞 翠绿
  - competitor_analyst: 🏎️ 紫
  - synthesis: 🎯 琥珀
- ✅ `<CopyButton>` 子组件
  - 消息气泡悬停时显示（右上角浮动）
  - 点击复制到剪贴板，显示 ✓ 1.5s 反馈
  - 使用 `lucide-react` 的 Copy/Check 图标
- ✅ 流式光标 `▌` 移到 Markdown 后面
- ✅ `npm run build` 通过（bundle 219kB → 378kB）

---

**目标**：textarea 替换 input，自动撑高；streaming 时显示停止按钮；空状态显示建议 prompt 卡片。

**改动文件**：
- `frontend/src/components/ChatWindow.tsx` — 输入框升级
- `frontend/src/components/SuggestedPrompts.tsx`（新建）— 4 个建议卡片
- `frontend/src/hooks/useSSE.ts` — 已有 `stopStream`，绑定到按钮

**进度记录**：✅ 完成于 2026-05-26

实际改动：
- ✅ 新建 `frontend/src/components/SuggestedPrompts.tsx`
  - 4 个建议卡片：赛前策略 / 赛后复盘 / 赛道信息 / F1 知识
  - 每卡有标题 + 完整 prompt + 一行提示
  - 鼠标悬停时边框变琥珀色
  - 点击直接发送对应 prompt
- ✅ `ChatWindow.tsx` 输入框升级
  - `<input>` → 自动撑高 `<textarea>`（rows=1, max-height=200px）
  - 通过 useEffect 监听 input 变化重计算高度
  - placeholder 加入 "Shift+Enter 换行" 提示
  - Enter 发送 / Shift+Enter 换行
- ✅ 流式时按钮切换：`Send 发送` → `⏹ 停止`
  - 停止用红色按钮 (`bg-red-500/90`)，发送用琥珀色
  - 使用 `lucide-react` 图标 (Send, Square)
- ✅ 停止后追加系统消息 "已停止生成"
- ✅ 空状态用 `<SuggestedPrompts>` 替换原静态文本
- ✅ `npm run build` 通过

UX 改进：
- 多行 prompt 现在可以正常输入和显示
- streaming 中可随时点击停止按钮中止
- 新对话时显示 4 个引导卡片，点击直接体验

---

**目标**：流式 Markdown 渲染、回到底部浮动按钮、重新生成、token 用量显示。

**改动文件**：
- `frontend/src/components/ChatWindow.tsx` — 滚动逻辑
- `frontend/src/components/MessageBubble.tsx` — 重新生成按钮

**进度记录**：✅ 完成于 2026-05-26

实际改动：

**后端**：
- ✅ `agents/base.py` — 开启 `stream_options={"include_usage": True}`，在流末尾抓取 usage 累加到 `token_tracker`
- ✅ `harness/orchestrator.py` — 在 `handle_prompt` 入口快照 token 起始值，结束时算 delta，写入 `complete` 事件

**前端**：
- ✅ `types/index.ts` — `complete` 事件增加 `usage` 字段
- ✅ `App.tsx` — 增加 `onChatComplete` 回调，每次对话完成刷新 Sidebar
- ✅ `ChatWindow.tsx` — 4 项改进：
  1. **智能自动滚动**：监听 scroll 事件，仅当用户在底部时才自动滚；向上翻看时不打扰
  2. **回到底部浮动按钮**：用户向上翻时右下角出现 `↓` 按钮，点击回到底部
  3. **重新生成按钮**：底部工具栏，找到最后一条 user 消息，丢弃之后的全部内容并重新发送
  4. **Token 用量显示**：底部工具栏显示"输入 N / 输出 M"

UX 改进：
- 长对话向上翻看历史时不再被自动滚动打断
- 点击"重新生成"可直接重试上次回复（不需要重新输入）
- 每次对话后 Sidebar 自动刷新，时间戳/消息数实时更新
- 底部状态栏显示 token 消耗，了解成本

---

**目标**：F1 红黑配色、轮胎配方徽章、车队 Logo、赛道缩略图。

**改动文件**：
- `frontend/src/index.css` — 主题配色变量
- `frontend/src/components/DataCard.tsx` — 轮胎/车队徽章
- 资源：F1 配色 `#E10600` 红 + `#15151E` 黑

**进度记录**：✅ 完成于 2026-05-26

实际改动：

**新增基础设施**：
- ✅ `frontend/src/index.css` — 新建
  - `@theme` 自定义 F1 配色 token (`f1-red`/`f1-black`/`f1-graphite`)
  - 全局字体设置（PingFang/Microsoft YaHei 中文优先）
  - 滚动条美化
  - 选中文字 F1 红
- ✅ `frontend/src/main.tsx` — 改为 `import './index.css'` 加载主题
- ✅ `frontend/src/utils/f1Theme.ts` — 新建
  - `TEAM_COLORS`：12 支车队官方配色
  - `getTeamColor(team)` 模糊匹配函数
  - `TIRE_COMPOUND_INFO`：SOFT/MEDIUM/HARD/INTERMEDIATE/WET 颜色 + 缩写
- ✅ `frontend/src/components/F1Badges.tsx` — 新建
  - `<TireBadge>`：彩色圆形徽章（红/黄/白），3 种尺寸
  - `<TeamColorStripe>`：车队配色竖条（排位赛卡片用）

**配色全局替换** amber → red：
- ✅ `App.tsx` — 顶栏增加 F1 红竖条标识
- ✅ `Sidebar.tsx` — 新对话 + 按钮 / 折叠态 + 按钮
- ✅ `ChatWindow.tsx` — 发送按钮改用 F1 红 `#E10600`，输入框焦点边框 red
- ✅ `SuggestedPrompts.tsx` — 卡片悬停边框 + 图标
- ✅ `MessageBubble.tsx`
  - 用户气泡背景 `#E10600`（醒目识别）
  - Synthesis Agent 徽章红色
  - 流式光标 `▌` / 加载点 `...` / 系统消息脉冲点
  - Markdown 链接 / 行内代码 改红色
- ✅ `ComparisonCard.tsx` — 预测文本红色

**数据卡片增强**：
- ✅ `DataCard.tsx`
  - 赛道卡片 emoji 🏁 + 红色标题
  - 天气卡片新增风速显示
  - 排位赛卡片：用 `TeamColorStripe` 显示车队配色竖条，车手名下方显示车队名

**策略卡片重做**：
- ✅ `StrategyCard.tsx`
  - 背景改 `from-red-950/30 to-zinc-950` 渐变
  - 边框 `border-red-600/40`
  - 标题右侧自动提取策略文本中的轮胎配方，显示彩色 `<TireBadge>`
  - 支持中英文配方提取（SOFT/MEDIUM/HARD / 软胎/中性胎/硬胎）

视觉差异：
- 旧：琥珀色单色系
- 新：F1 红 + 车队彩色 + 轮胎彩色徽章，更专业
- 界面层次：CSS 文件独立打包（25kB），主题集中管理

---

## 升级完成总结

| 步骤 | 主要新增 |
|------|---------|
| Step 1 | 后端会话持久化（5 个 API + JSON 存储） |
| Step 2 | Sidebar + 历史会话切换 |
| Step 3 | Markdown 渲染 + Copy 按钮 + Agent 徽章 |
| Step 4 | 多行 textarea + 停止按钮 + 建议卡片 |
| Step 5 | 智能滚动 + 回底按钮 + 重新生成 + Token 用量 |
| Step 6 | F1 红黑主题 + 轮胎/车队彩色徽章 |

最终 bundle：375kB JS + 25kB CSS（gzip 后约 120kB）。

---

## 启动方式

```bash
# 后端（需要重启以加载 token 追踪和 session 端点）
lsof -ti:8000 | xargs kill -9 2>/dev/null
./run_backend.sh

# 前端（新终端）
cd frontend && npm run dev
```

浏览器访问 `http://localhost:5173`。

```bash
./run_backend.sh                # 后端
cd frontend && npm run dev      # 前端
```