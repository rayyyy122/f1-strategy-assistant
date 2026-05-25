# F1 策略助手 — 实现方案

## Context

从零开发一个面向 F1 方程式赛车的多 Agent 策略助手，采用**对话框式交互**。

核心工作模式：
1. **赛前策略分析**：用户输入自然语言 prompt → 意图路由 → 加载比赛数据 → 多 Agent 协作推理 → 流式返回策略建议
2. **赛后复盘对比**：加载实际比赛结果 → 与 Agent 预测对比 → 差异分析
3. **快速问答**：赛道信息、历史数据、F1 知识等单 Agent 快速响应
4. **多轮追问**：支持用户在对话中追问（"如果安全车在第15圈出现呢？"）

技术约束：简洁 Demo、支持外部 LLM API、预留 RL 训练接口。

---

## 1. 项目结构

```
f1-strategy-assistant/
├── backend/
│   ├── main.py                  # FastAPI 入口 + SSE 路由
│   ├── config.py                # 配置（LLM API key、缓存路径等）
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py              # Agent 基类（通用 LLM 调用、工具调用循环）
│   │   ├── race_context.py      # Race Context Analyst
│   │   ├── tire_strategist.py   # Tire Strategy Analyst
│   │   ├── competitor_analyst.py # Competitor Analyst
│   │   └── synthesis.py         # Synthesis Strategist
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py          # 工具注册中心（所有工具的声明和路由）
│   │   ├── circuit_tools.py     # 赛道信息工具
│   │   ├── weather_tools.py     # 天气数据工具
│   │   ├── session_tools.py     # 练习赛/排位赛数据工具
│   │   ├── tire_tools.py        # 轮胎退化计算工具
│   │   └── strategy_tools.py    # 策略对比/模拟工具
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fastf1_client.py     # FastF1 数据加载封装
│   │   ├── openf1_client.py     # OpenF1 API 客户端
│   │   └── jolpica_client.py    # Jolpica API 客户端
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── manager.py           # 记忆管理器（三层记忆的统一接口）
│   │   └── trace_store.py       # RL 轨迹存储（JSONL 读写）
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── orchestrator.py      # Agent 编排器（控制 Agent 调用顺序）
│   │   ├── router.py            # 意图路由器（prompt → mode + 参数提取）
│   │   ├── guardrails.py        # 策略合理性校验
│   │   └── logger.py            # 全链路日志
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py           # Pydantic 数据模型
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx         # 主容器：消息列表 + 输入框
│   │   │   ├── MessageBubble.tsx      # 通用消息气泡（用户/AI/系统，支持子类型渲染）
│   │   │   ├── DataCard.tsx           # 数据卡片（赛道/天气/排位/练习赛）
│   │   │   ├── AgentThinkingBlock.tsx # 可折叠的 Agent 推理过程
│   │   │   └── StrategyCard.tsx       # 策略建议高亮卡片
│   │   ├── hooks/
│   │   │   └── useSSE.ts              # SSE 流式数据 hook
│   │   ├── types/
│   │   │   └── index.ts
│   │   └── utils/
│   │       └── api.ts                 # API 请求封装
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
└── README.md
```

---

## 2. 架构设计

### 2.1 整体分层

```
┌─────────────────────────────────┐
│  Frontend (React + Vite)        │  ← 对话框式 UI, SSE 流式消费
├─────────────────────────────────┤
│  FastAPI (REST + SSE)           │  ← /api/chat (核心端点)
├─────────────────────────────────┤
│  Harness Layer                  │
│  · Router (prompt → mode 路由)   │
│  · Orchestrator (编排流程)       │
│  · Guardrails (输出校验)         │
│  · Logger (全链路日志+token追踪)  │
├─────────────────────────────────┤
│  Agent Layer                    │
│  · 4 个 Agent + 1 个 Router     │
│  · base.py 提供通用 LLM+Tool 循环│
├─────────────────────────────────┤
│  Memory Layer                   │
│  · 短期 (对话历史)                │
│  · 工作 (结构化中间结果)          │
│  · 长期 (JSONL 轨迹+SQLite 缓存) │
├─────────────────────────────────┤
│  Tool Layer                     │
│  · 工具注册 + 函数实现            │
├─────────────────────────────────┤
│  Data Layer                     │
│  · FastF1 / OpenF1 / Jolpica    │
└─────────────────────────────────┘
```

### 2.2 Agent 基类设计 — 核心抽象

```python
class BaseAgent:
    """所有 Agent 的基类，封装 Claude API 调用 + 工具循环"""

    name: str
    system_prompt: str
    model: str = "claude-opus-4-7"          # 默认模型
    effort: str = "high"                     # low | medium | high | xhigh | max
    tools: list[Tool]
    llm_client: anthropic.Anthropic          # 外部 LLM API 客户端

    async def run(
        self,
        context: dict,
        memory: MemoryManager,
        event_queue: asyncio.Queue,           # SSE 事件队列（流式推送）
    ) -> AgentOutput:
        """标准 Agent 循环（streaming + tool use）：

        1. 构建 messages（system_prompt + context + 上游 Agent 输出）
        2. 启用 prompt caching（system_prompt + tools 自动缓存）
        3. streaming 调用 Claude API（adaptive thinking + effort）
        4. 流式推送 thinking/text 到前端
        5. 如果 stop_reason == "tool_use" → 执行工具 → 追加 tool_result → 回到步骤 3
        6. 如果 stop_reason == "end_turn" → 解析最终输出 → 返回
        7. 如果 stop_reason == "refusal" → 记录并返回错误
        """
        messages = self._build_messages(context, memory)

        while True:
            with self.llm_client.messages.stream(
                model=self.model,
                max_tokens=64000,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},     # 自动缓存 system+ tools
                system=self.system_prompt,
                tools=self._get_tool_schemas(),
                messages=messages,
            ) as stream:
                # 流式推送 thinking 和 text 到前端
                for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "thinking_delta":
                            yield SSEvent("agent_thinking",
                                          agent=self.name,
                                          delta=event.delta.thinking)
                        elif event.delta.type == "text_delta":
                            yield SSEvent("agent_text",
                                          agent=self.name,
                                          delta=event.delta.text)

                response = stream.get_final_message()

            # 处理 stop_reason
            if response.stop_reason == "end_turn":
                break
            elif response.stop_reason == "refusal":
                raise AgentRefusalError(response.stop_details)
            elif response.stop_reason == "tool_use":
                # 执行工具，追加 assistant 消息 + tool_result
                messages.append({"role": "assistant", "content": response.content})
                tool_results = await self._execute_tools(response.content)
                messages.append({"role": "user", "content": tool_results})
            elif response.stop_reason == "pause_turn":
                # server-side tool 达到迭代上限，继续
                messages.append({"role": "assistant", "content": response.content})

        return self._parse_output(response)
```

**模型 & effort 分层策略**：

| Agent | 模型 | effort | 理由 |
|-------|------|--------|------|
| Race Context | `claude-opus-4-7` | `high` | 需要综合赛道+历史+天气信息，中等推理需求 |
| Tire Strategist | `claude-opus-4-7` | `high` | 需要数据分析和数学推理 |
| Competitor Analyst | `claude-opus-4-7` | `high` | 需要对比分析和趋势判断 |
| Synthesis Strategist | `claude-opus-4-7` | `xhigh` | 汇总多源信息、权衡矛盾、最终决策，需要最深推理 |

> **注意**：所有 Agent 使用同一模型以保持 prompt cache 有效。切换模型会清空缓存。如果后期需要降成本，专项分析 Agent 可换 Sonnet 4.6，但需评估缓存收益损失。

### 2.3 工具注册机制

```python
class ToolRegistry:
    """全局工具注册中心，每个工具是一个可调用的函数 + 描述 schema"""

    tools: dict[str, Tool]

    def register(self, func, description, parameters_schema):
        """注册工具，自动生成 LLM function-calling 的 JSON schema"""

    def execute(self, tool_name: str, params: dict) -> ToolResult:
        """执行工具调用"""

    def get_schema_for_agent(self, agent_name: str) -> list[dict]:
        """获取该 Agent 可用工具的 OpenAI function-calling schema 列表"""
```

### 2.4 编排流程

```
POST /api/analyze?race={round}&season={year}
         │
         ▼
┌─ Orchestrator ─────────────────────────────────────┐
│                                                      │
│  Step 1: 数据加载（并行）                             │
│    · 赛道信息 ← Jolpica                              │
│    · 天气预测 ← OpenF1                               │
│    · 练习赛数据 ← FastF1                             │
│    · 排位赛数据 ← Jolpica                            │
│                                                      │
│  Step 2: Agent 并行分析                              │
│    · Race Context Analyst ──┐                       │
│    · Tire Strategist ───────┤  SSE 流式推送          │
│    · Competitor Analyst ────┘  每个 Agent 输出        │
│                                                      │
│  Step 3: Synthesis Strategist                       │
│    · 汇总上游输出 → 生成最终策略                      │
│                                                      │
│  Step 4: 存入记忆 + 轨迹                              │
│    · 工作记忆 ← 所有 Agent 输出                       │
│    · 轨迹文件 ← 完整推理链（RL 预留）                  │
└──────────────────────────────────────────────────────┘
```

### 2.5 意图路由设计

用户输入自然语言 → Router 分类 → 匹配 mode + 提取参数 + 选择 Agent 组合。

```
用户 prompt: "分析一下2024摩纳哥大奖赛的轮胎策略"
         │
         ▼
┌─ Intent Router (轻量 LLM 调用, Haiku/Sonnet) ─┐
│                                                  │
│  输出:                                           │
│  {                                               │
│    "mode": "pre_race",                           │
│    "season": 2024,                               │
│    "round": 8,                                   │
│    "params": {"focus": "tire_strategy"}          │
│  }                                               │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
              Orchestrator 根据 mode 调度 Agent
```

**支持的模式**：

| mode | 触发示例 | Agent 组合 | 说明 |
|------|---------|-----------|------|
| `pre_race` | "分析摩纳哥站策略"、"预测谁能夺冠" | Race Context → Tire + Competitor (并行) → Synthesis | 完整 4 Agent 流程 |
| `post_race` | "对比预测和实际结果"、"复盘摩纳哥站" | Comparison Agent | 加载实际结果 + 历史预测 → 对比 |
| `track_info` | "摩纳哥赛道特点"、"银石的历史" | Race Context (tool-only) | 仅工具查询，不跑 Agent 推理 |
| `quick_question` | "谁是今年冠军热门"、"DRS是什么" | Race Context | 单 Agent 快速回答 |
| `follow_up` | "如果安全车出现呢？" | 继承上一轮 mode + 上下文 | 多轮追问 |

**Router 实现**：

```python
class IntentRouter:
    """轻量级意图分类器——用 Haiku 做路由，低延迟低成本"""

    model: str = "claude-haiku-4-5"
    
    async def classify(self, prompt: str, history: list) -> Intent:
        """返回 Intent(mode, season, round, params)
        
        用 output_config.format 约束输出为固定 JSON Schema，
        Haiku 的延迟 ~200ms，分类准确率 >95%。
        """
```

Router 使用 Haiku 4.5（最快最便宜）+ `output_config.format` 约束输出 JSON Schema，保证延迟低、成本低、输出格式稳定。

**多轮对话支持**：

```
用户: "分析2024摩纳哥站的轮胎策略"
  → mode: pre_race, 运行全流程，结果存入 ShortTermMemory

用户: "如果安全车在第15圈出现呢？"
  → 检测到追问（无新 season/round 参数）
  → mode: follow_up, 继承上轮 context，仅运行 Synthesis
```

### 2.6 Prompt Caching 设计

**核心原则**：prompt cache 是**前缀匹配**——任何字节变化会使断点之后的所有缓存失效。渲染顺序是 `tools → system → messages`。

**缓存分层策略**：

```
请求结构（从前到后）:
┌──────────────────────────────────────────────┐
│ tools (固定, 按名称排序)                       │ ← 位置 0, 最先渲染
│ system prompt (冻结, 不插时间/ID)              │ ← cache_control 断点 ①
│ 比赛数据上下文 (同场比赛多次请求共享)            │ ← cache_control 断点 ②
│ 上游 Agent 输出 (相同分析会话内共享)            │
│ 用户具体问题 / 当前 Agent 任务                  │ ← 不缓存 (每次不同)
└──────────────────────────────────────────────┘
```

**具体实施**：

1. **System prompt 冻结**——不插入 `datetime.now()`、UUID、用户 ID 等动态内容。动态信息通过 `messages` 中的 user message 传递。

2. **工具列表确定性排序**——`ToolRegistry.get_schema_for_agent()` 按工具名排序，保证每次返回相同顺序。

3. **比赛数据缓存**——同一场比赛的赛道信息、天气、排位数据是固定的，放在第二个断点前。多个用户分析同一场比赛时共享此缓存。

4. **使用 top-level auto-caching**：

   ```python
   # BaseAgent.run() 中，cache_control 自动缓存最后一个 cacheable block
   response = client.messages.create(
       model="claude-opus-4-7",
       max_tokens=64000,
       cache_control={"type": "ephemeral"},  # 5 分钟 TTL, 自动放置
       system=agent.system_prompt,           # 冻结的 system prompt
       tools=tool_schemas,                   # 确定性排序
       messages=messages,
   )
   ```

5. **验证缓存命中**：

   ```python
   # 日志中记录缓存指标
   logger.info(
       f"cache_read={response.usage.cache_read_input_tokens}, "
       f"cache_write={response.usage.cache_creation_input_tokens}, "
       f"uncached={response.usage.input_tokens}"
   )
   ```

   `cache_read_input_tokens > 0` 表示命中缓存（~0.1x 价格），
   `cache_creation_input_tokens > 0` 表示正在写入缓存（首次请求，~1.25x 价格）。

**预期效果**：同一 Agent 的第二次请求起，system prompt + tools 从缓存读取，节省 ~90% 的 input token 成本。同场比赛的赛道/天气数据也从缓存读取。

**禁止事项**（防止静默缓存失效）：

-   `datetime.now()` / UUID 出现在 system prompt 中
-   工具列表顺序不稳定（使用 `sort_keys=True` 或按名称排序）
-   同一 Agent 在不同请求中使用不同 model（切换 model 清空缓存）

### 2.8 SSE 事件流设计

```
event: routing
data: {"mode": "pre_race", "season": 2024, "round": 8, "message": "识别为：赛前策略分析 · 摩纳哥大奖赛"}

event: progress
data: {"step": "loading", "message": "正在加载摩纳哥大奖赛数据..."}

event: data_card
data: {"card_type": "track", "data": {...}}       # 赛道信息卡片
data: {"card_type": "weather", "data": {...}}     # 天气卡片
data: {"card_type": "qualifying", "data": [...]}   # 排位赛卡片
data: {"card_type": "practice", "data": {...}}     # 练习赛卡片

event: agent_start
data: {"agent": "race_context", "message": "Race Context 分析中..."}

event: agent_thinking
data: {"agent": "tire_strategist", "delta": "分析FP2长距离数据..."}

event: agent_text
data: {"agent": "tire_strategist", "delta": "建议一停策略，进站窗口第18-22圈"}

event: agent_tool_call
data: {"agent": "tire_strategist", "tool": "calc_degradation_curve", "params": {...}}

event: agent_tool_result
data: {"agent": "tire_strategist", "tool": "calc_degradation_curve", "result": {...}}

event: agent_complete
data: {"agent": "race_context", "output": {...}}

event: strategy_card
data: {"strategy": {...}, "confidence": 0.82, "alternatives": [...]}

event: complete
data: {"trace_id": "2025_Monaco_20250524", "usage": {"total_tokens": 45000}}
```

事件类型对应前端渲染：

| 事件 | 前端渲染 |
|------|---------|
| `routing` | 居中灰色小字 "识别为：赛前策略分析" |
| `progress` | 居中加载指示器 |
| `data_card` | 内嵌数据卡片（赛道/天气/排位/练习赛） |
| `agent_start` | 新建 AI 气泡，显示 Agent 名称 |
| `agent_thinking` | 气泡内折叠区域，点击展开推理过程 |
| `agent_text` | 气泡内流式文本，有打字机效果 |
| `agent_tool_call` / `agent_tool_result` | 折叠展示工具调用详情（可选） |
| `agent_complete` | Agent 状态标记完成 |
| `strategy_card` | 高亮策略建议卡片 |
| `complete` | 显示 token 用量 |
```

---

## 3. 分阶段实现计划

### Phase 1: 数据层 + 工具层

**目标**：跑通 F1 数据管道，能加载任意比赛的赛道信息、天气、练习赛、排位赛数据。

**文件清单**（按实现顺序）：

1. `backend/config.py`
   - LLM API URL / API Key（从环境变量读取）
   - 缓存目录配置
   - FastF1 缓存开关

2. `backend/data/fastf1_client.py`
   - `load_session(year, round, session_type)` → 加载练习赛/排位赛/正赛数据
   - `get_lap_times(session)` → 所有车手圈速 DataFrame
   - `get_tire_data(session)` → 轮胎配方和使用圈数
   - `get_weather(session)` → 赛道天气数据
   - 启用 FastF1 内置缓存

3. `backend/data/jolpica_client.py`
   - `get_season_schedule(year)` → 赛季日程
   - `get_circuit_info(circuit_id)` → 赛道详情
   - `get_qualifying_results(year, round)` → 排位赛结果
   - `get_driver_standings(year)` → 车手积分榜

4. `backend/data/openf1_client.py`
   - `get_weather_forecast(session_key)` → 天气预测
   - 后续可扩展更多实时数据端点

5. `backend/tools/registry.py`
   - `ToolRegistry` 类：注册、查询、执行
   - 工具 schema 自动生成（Python 函数 → OpenAI function-calling JSON）

6. `backend/tools/circuit_tools.py`
   - `get_circuit_profile(track_name)` — 赛道信息摘要
   - `get_historical_strategies(track_name, years)` — 历史策略模式

7. `backend/tools/weather_tools.py`
   - `get_weather_forecast(session)` — 天气预测

8. `backend/tools/session_tools.py`
   - `get_practice_longruns(session, compound)` — 长距离圈速
   - `get_qualifying_results(year, round)` — 排位结果

9. `backend/tools/tire_tools.py`
   - `calc_degradation_curve(lap_times)` — 退化率计算
   - `estimate_stint_length(compound, track)` — 预估单段里程

10. `backend/tools/strategy_tools.py`
    - `compare_strategies(options)` — 策略对比
    - `simulate_race_outcome(strategy, conditions)` — 简化模拟

11. `backend/models/schemas.py`
    - Pydantic 模型：`TrackInfo`, `WeatherData`, `QualifyingResult`, `PracticeData`, `AgentOutput`, `StrategyResult`

**验证方式**：运行 `python -m backend.data.fastf1_client` 能加载 2024 摩纳哥大奖赛数据并打印摘要。

---

### Phase 2: Agent 层 + 记忆层 + Harness 层

**目标**：实现 4 个 Agent 的完整推理流程，LLM 调用 + 工具选择，输出结构化结果。

**文件清单**（按实现顺序）：

1. `backend/agents/base.py`
   - `BaseAgent` 类：标准 Agent 循环（streaming + tool use + stop_reason 处理）
   - `LLMClient` 封装：基于 `anthropic.Anthropic`，支持 adaptive thinking + effort + prompt caching
   - `AgentOutput` 数据类：统一结构化输出（Pydantic 模型）
   - `AgentRefusalError`：安全拒绝异常

2. `backend/agents/race_context.py`
   - System prompt: "你是 F1 赛道分析专家..."（冻结，不插时间/ID）
   - 可用工具: `get_circuit_profile`, `get_historical_strategies`, `get_weather_forecast`
   - 输出: `RaceContextOutput` (Pydantic) — 赛道特性报告 + 天气影响评估 + 历史模式总结

3. `backend/agents/tire_strategist.py`
   - System prompt: "你是 F1 轮胎策略专家..."
   - 可用工具: `get_practice_longruns`, `calc_degradation_curve`, `estimate_stint_length`
   - 输出: `TireStrategyOutput` (Pydantic) — 推荐轮胎配方 + 进站窗口 + 一停/二停对比 + 退化率

4. `backend/agents/competitor_analyst.py`
   - System prompt: "你是 F1 竞争对手分析专家..."
   - 可用工具: `get_qualifying_results`, `get_driver_form`
   - 输出: `CompetitorOutput` (Pydantic) — 起跑威胁排序 + 对手状态评估 + 潜在竞争格局

5. `backend/agents/synthesis.py`
   - System prompt: "你是 F1 首席策略师..."
   - 无需额外工具（汇总上游 Agent 的结构化输出）
   - 输出: `SynthesisOutput` (Pydantic) — 最终策略建议 + 备选方案 + 关键假设 + 置信度
   - 使用 `output_config.format` 约束输出为 JSON Schema

每个 Agent 的输出使用 Pydantic 模型 + `output_config.format` 约束，确保结构化，方便下游解析和 RL 轨迹记录：

```python
from pydantic import BaseModel
from typing import Optional

class TireStrategyOutput(BaseModel):
    recommended_compound: str          # "MEDIUM" | "HARD" | "SOFT"
    pit_window_start: int              # 进站窗口起始圈数
    pit_window_end: int                # 进站窗口结束圈数
    degradation_rate: float            # 退化率 (s/lap)
    stint_length_estimate: int         # 预估单段圈数
    alternatives: list[str]            # 备选方案说明
    confidence: float                  # 0-1
    reasoning: str                     # 推理摘要
```

所有 Agent 的输出定义在 `backend/models/schemas.py` 中。

6. `backend/memory/manager.py`
   - `ShortTermMemory`：对话上下文管理（简单 dict）
   - `WorkingMemory`：当前分析会话的结构化中间结果（Pydantic models → dict）
   - `LongTermMemory`：SQLite 持久化（缓存 + 预测历史）

7. `backend/memory/trace_store.py`
   - `save_trace(trace: dict)` → JSONL 追加写入
   - `load_traces(race_id: str)` → 按比赛加载
   - 轨迹格式符合 RL 训练要求（state, action, reward, planning_chain）

8. `backend/harness/router.py`
   - `IntentRouter.classify(prompt, history)` → `Intent(mode, season, round, params)`
   - 使用 Haiku 4.5 + `output_config.format` 做快速分类
   - 模式: `pre_race` | `post_race` | `track_info` | `quick_question` | `follow_up`

9. `backend/harness/orchestrator.py`
   - `Orchestrator.handle_prompt(prompt, history)` → SSE 流
   - 先调用 Router 分类，再根据 mode 调度 Agent
   - 异步并行执行 Race Context / Tire / Competitor
   - SSE 事件发射（使用 asyncio.Queue）

10. `backend/harness/guardrails.py`
   - 策略合理性校验：进站圈数是否在实际范围、轮胎配方是否合理
   - 输出格式校验：Pydantic 模型验证
   - 异常处理：捕获 `AgentRefusalError`、`RateLimitError`、`APIStatusError`

11. `backend/harness/logger.py`
    - 结构化日志：时间戳 + Agent 名 + 事件类型 + 内容
    - Token 使用追踪：记录每次 LLM 调用的 `input_tokens`、`output_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`
    - 输出到 stdout（后续可接文件/数据库）

**验证方式**：运行 Orchestrator 发送 "分析2024摩纳哥站策略"，能看到 Router 分类为 `pre_race`，然后 3 个 Agent 并行执行 + Synthesis 汇总。

---

### Phase 3: FastAPI 后端 + SSE 流式输出

**目标**：将 Phase 2 的编排器通过 FastAPI 暴露为 SSE 接口，支持对话式交互。

**文件清单**：

1. `backend/main.py`
   - `GET /api/health` — 健康检查
   - `GET /api/races?season={year}` — 返回赛季日程（供前端输入补全或下拉）
   - `POST /api/chat` — **核心端点**，接收 `{prompt, history}`，运行 Router → Orchestrator → SSE 流式返回
   - CORS 配置（允许前端跨域）

2. `POST /api/chat` 请求/响应格式：

   ```json
   // 请求
   {
     "prompt": "分析一下2024摩纳哥大奖赛的轮胎策略",
     "history": [
       {"role": "user", "content": "..."},
       {"role": "assistant", "content": "..."}
     ]
   }

   // 响应: SSE text/event-stream
   ```

3. SSE 流式实现要点：
   - 使用 `StreamingResponse` + `text/event-stream`
   - Orchestrator 通过 asyncio.Queue 发送事件
   - Router 分类结果作为首个 `routing` 事件推送
   - 数据卡片通过 `data_card` 事件推送，前端渲染为内嵌卡片
   - 每个 Agent 的 thinking/text 流式推送到对应气泡

4. `backend/requirements.txt`
   - fastapi, uvicorn[standard], anthropic, httpx, fastf1, pandas, pydantic

**验证方式**：启动 `uvicorn main:app --reload`，用 curl 测试：
```bash
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"分析2024摩纳哥站策略","history":[]}'
```
能看到流式 SSE 事件：`routing` → `progress` → `data_card` → `agent_*` → `strategy_card` → `complete`。

---

### Phase 4: React 前端 — 对话框式交互

**目标**：实现简洁的对话框 UI，用户输入自然语言 prompt，流式展示 Agent 推理和结果。

**文件清单**（按实现顺序）：

1. `frontend/package.json` → React 18 + Vite + Tailwind CSS
2. `frontend/vite.config.ts` → 基础配置 + API 代理（`/api` → `localhost:8000`）
3. `frontend/src/types/index.ts` → TypeScript 类型定义（`Message`, `SSEEvent`, `DataCard` 等）
4. `frontend/src/utils/api.ts` → `POST /api/chat` 请求封装 + SSE 解析
5. `frontend/src/hooks/useSSE.ts` → SSE 事件解析 hook，按事件类型分发给 reducer
6. `frontend/src/components/ChatWindow.tsx` → 主容器：消息列表（自动滚动到底部）+ 底部输入框
7. `frontend/src/components/MessageBubble.tsx` → 通用消息气泡，根据 `message.type` 渲染不同子组件：
   - `user` → 右对齐文本气泡
   - `routing` → 居中灰色小字
   - `progress` → 居中加载指示器 + 文字
   - `data_card` → 内嵌 `DataCard` 组件
   - `agent` → 左对齐气泡，包含 `AgentThinkingBlock` + 流式文本
   - `strategy_card` → 内嵌 `StrategyCard` 组件
8. `frontend/src/components/DataCard.tsx` → 数据卡片，根据 `card_type` 渲染不同样式：
   - `track` → 赛道名、长度、弯道数、DRS 区、超车难度
   - `weather` → 气温、赛道温度、降雨概率、风速
   - `qualifying` → 前 5 名表格
   - `practice` → 各配方轮胎圈速 + 退化率
9. `frontend/src/components/AgentThinkingBlock.tsx` → 可折叠区域，默认折叠，点击展开 Agent 推理过程
10. `frontend/src/components/StrategyCard.tsx` → 高亮策略卡片：轮胎方案、进站窗口、预测完赛、风险提示
11. `frontend/src/App.tsx` → 布局组合：顶部标题栏 + ChatWindow
12. `frontend/tailwind.config.js` → Tailwind 配置

**前端布局**：

```
┌─────────────────────────────────────────────────┐
│  🏎️ F1 策略助手                                   │
│  ┌─────────────────────────────────────────────┐│
│  │                                             ││
│  │  [用户] 分析一下2024摩纳哥大奖赛的轮胎策略      ││
│  │                                             ││
│  │  [系统] 识别为：赛前策略分析 · 摩纳哥大奖赛      ││
│  │         ⏳ 正在加载比赛数据...                 ││
│  │                                             ││
│  │  ┌─ 赛道信息 ────────────────────────────┐  ││
│  │  │ 蒙特卡洛 · 3.337km · 19弯 · 超车极难   │  ││
│  │  │ 天气: 晴 22°C · 降雨概率 10%          │  ││
│  │  └──────────────────────────────────────┘  ││
│  │  ┌─ 排位赛结果 ──────────────────────────┐  ││
│  │  │ P1 Leclerc 1:10.270                  │  ││
│  │  │ P2 Piastri 1:10.424                  │  ││
│  │  │ P3 Sainz   1:10.518                  │  ││
│  │  └──────────────────────────────────────┘  ││
│  │                                             ││
│  │  ┌─ Tire Strategist ─────────────────────┐  ││
│  │  │ ▶ 推理过程 (点击展开)                   │  ││
│  │  │ 建议一停策略，进站窗口第18-22圈换硬胎     │  ││
│  │  │ 中性胎退化率 0.08s/圈，硬胎 0.04s/圈    │  ││
│  │  └──────────────────────────────────────┘  ││
│  │                                             ││
│  │  ┌─ 🎯 策略建议 ─────────────────────────┐  ││
│  │  │ 中性胎起步 → L22换硬胎 → 预测P1完赛     │  ││
│  │  │ 关键风险: 安全车概率35%  置信度: 0.82  │  ││
│  │  └──────────────────────────────────────┘  ││
│  │                                             ││
│  │  [用户] 如果安全车在第15圈出现呢?             ││
│  │  [Synthesis] 好问题。安全车在L15出现会...    ││
│  │                                             ││
│  ├─────────────────────────────────────────────┤│
│  │ ✍️ 输入你的F1策略问题...              [发送] ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**状态管理**：

```typescript
// App.tsx 中的状态
interface ChatState {
  messages: Message[];        // 消息列表
  isStreaming: boolean;       // 是否正在接收 SSE 流
  activeAgents: Set<string>;  // 当前正在工作的 Agent
}

// Message 类型
type Message =
  | { type: "user"; text: string }
  | { type: "routing"; mode: string; message: string }
  | { type: "progress"; text: string }
  | { type: "data_card"; cardType: string; data: object }
  | { type: "agent_start"; agent: string }
  | { type: "agent_thinking"; agent: string; delta: string }
  | { type: "agent_text"; agent: string; delta: string }
  | { type: "agent_complete"; agent: string }
  | { type: "strategy_card"; strategy: object }
  | { type: "complete"; usage: object }
  | { type: "error"; text: string };
```

**消息流处理**（useSSE hook）：

1. 用户点击发送 → `POST /api/chat`，建立 SSE 连接
2. 收到 `routing` → 新增系统消息 "识别为：xxx"
3. 收到 `progress` → 新增/更新进度消息
4. 收到 `data_card` → 新增数据卡片消息
5. 收到 `agent_start` → 新建 Agent 气泡（loading 状态）
6. 收到 `agent_thinking` → 追加到对应 Agent 气泡的折叠区域
7. 收到 `agent_text` → 流式追加到对应 Agent 气泡的文本
8. 收到 `agent_complete` → 标记 Agent 完成
9. 收到 `strategy_card` → 新增高亮策略卡片
10. 收到 `complete` → 结束 streaming，显示 token 用量
11. 用户可继续输入 prompt 追问

**验证方式**：`npm run dev`，在输入框输入"分析2024摩纳哥站策略"，能看到：
- 系统识别消息 → 数据卡片加载 → Agent 气泡逐个出现并流式输出 → 策略卡片 → 可追问

---

### Phase 5: RL 轨迹 + 策略对比（闭环）

**目标**：赛后回填真实结果，自动计算预测准确率，完善 RL 训练数据格式。

**文件清单**：

1. `backend/memory/trace_store.py` 扩展
   - `backfill_outcome(trace_id)` → 赛后回填真实结果
   - `compute_accuracy(season)` → 统计预测准确率
   - Trace 格式标准化

2. `backend/tools/strategy_tools.py` 扩展
   - `load_actual_race_result(year, round)` → 加载真实比赛结果
   - `compare_prediction_vs_actual(trace_id)` → 对比预测 vs 实际

3. `frontend/src/components/StrategyCard.tsx` 扩展 → 赛后对比时显示 Agent 预测 vs 实际结果并排对比

**验证方式**：分析一场已完成比赛，赛后调用回填接口，能看到预测 vs 实际对比和准确率。

---

## 4. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 交互方式 | 对话框式（自然语言 prompt） | 比固定面板更灵活，支持多轮追问和多种任务模式 |
| 意图路由 | Haiku 4.5 + `output_config.format` | 低延迟 (~200ms)、低成本、输出格式稳定 |
| Agent 编排 | 手写 Agent Loop | 不依赖 LangChain/Managed Agents，方便 RL 改造，代码量小 |
| LLM API | Anthropic Python SDK (`anthropic`) | 原生 SDK，支持 streaming + prompt caching + adaptive thinking |
| 模型选择 | Opus 4.7 (分析) + Haiku 4.5 (路由) | Opus 负责深度推理，Haiku 负责快速分类 |
| Thinking 模式 | `adaptive` (自适应) | 取代手动 `budget_tokens`，Claude 自动决定思考深度 |
| Effort 分层 | Synthesis=xhigh, 其他=high | Synthesis 需要最深推理，专项分析用 high 平衡质量与成本 |
| Prompt Caching | 冻结 system prompt + tools，top-level auto-caching | 节省 ~90% input token 成本；动态信息通过 messages 传递 |
| 工具调用 | OpenAI function-calling 格式 | 最通用的工具调用协议 |
| Agent 通信 | 串行汇总 + 结构化输出 | Pydantic 输出便于下游解析和 RL 轨迹记录 |
| Agent 输出格式 | Pydantic + `output_config.format` | JSON Schema 约束，结构化，方便 Synthesis 解析和 RL 训练 |
| 前后端通信 | SSE (单向流式) | 比 WebSocket 更简单，满足流式推送需求 |
| 前端状态管理 | React useState/useReducer | 单页面应用，消息列表 + 流式追加 |
| 数据缓存 | FastF1 内置缓存 + SQLite | FastF1 自带文件缓存，SQLite 存策略历史和用户记忆 |
| RL 轨迹格式 | JSONL | 每行一条完整轨迹 (state, action, reward, planning_chain) |
| 错误处理 | SDK typed exceptions | `RateLimitError`、`APIStatusError` 等，不靠字符串匹配 |

---

## 6. 实现进度

### Phase 1: 数据层 + 工具层 ✅ 已完成

| 文件 | 状态 |
|------|------|
| `backend/requirements.txt` | ✅ |
| `backend/config.py` | ✅ |
| `backend/llm_client.py` | ✅ |
| `backend/models/schemas.py` | ✅ 13 个 Pydantic 模型 |
| `backend/data/fastf1_client.py` | ✅ 5 个函数 |
| `backend/data/jolpica_client.py` | ✅ 4 个函数 |
| `backend/data/openf1_client.py` | ✅ |
| `backend/tools/registry.py` | ✅ 工具注册/查询/执行 + Agent 权限 |
| `backend/tools/circuit_tools.py` | ✅ 2 个工具：赛道信息 + 历史策略 |
| `backend/tools/weather_tools.py` | ✅ 1 个工具：天气 |
| `backend/tools/session_tools.py` | ✅ 3 个工具：长距离 + 排位 + 车手状态 |
| `backend/tools/tire_tools.py` | ✅ 2 个工具：退化率 + 可用圈数 |
| `backend/tools/strategy_tools.py` | ✅ 2 个工具：实际结果 + 预测对比 |

**共 10 个工具，分布于 4 个 Agent。**

### Phase 2: Agent 层 + 记忆层 + Harness 层 ✅ 已完成

| 文件 | 状态 |
|------|------|
| `backend/agents/base.py` | ✅ streaming + tool use 循环 + 6 种 stop_reason + prompt caching |
| `backend/agents/race_context.py` | ✅ 4 个工具，high effort |
| `backend/agents/tire_strategist.py` | ✅ 3 个工具，high effort |
| `backend/agents/competitor_analyst.py` | ✅ 3 个工具，high effort |
| `backend/agents/synthesis.py` | ✅ 无工具（纯汇总），xhigh effort |
| `backend/memory/manager.py` | ✅ ShortTermMemory + WorkingMemory |
| `backend/memory/trace_store.py` | ✅ save / load / backfill / compute_accuracy |
| `backend/harness/router.py` | ✅ Haiku 4.5 分类到 5 种 mode |
| `backend/harness/orchestrator.py` | ✅ 路由→数据→Agent 调度→SSE→轨迹 |
| `backend/harness/guardrails.py` | ✅ 策略校验 |
| `backend/harness/logger.py` | ✅ 结构化日志 + TokenTracker |

### Phase 3: FastAPI 后端 + SSE 端点 ✅ 已完成

| 文件 | 状态 |
|------|------|
| `backend/main.py` | ✅ FastAPI + 2 个端点 + CORS + SSE 流式 |
| `POST /api/chat` | ✅ 核心端点，SSE text/event-stream |
| `GET /api/health` | ✅ 健康检查 |
| 会话记忆管理 | ✅ 基于 session_id 的 MemoryManager |

### Phase 4: React 前端 ✅ 已完成

| 文件 | 状态 |
|------|------|
| `vite.config.ts` | ✅ Tailwind CSS v4 + API 代理 |
| `src/types/index.ts` | ✅ 12 个 TypeScript 类型 |
| `src/utils/api.ts` | ✅ POST /api/chat + health check |
| `src/hooks/useSSE.ts` | ✅ SSE 流式解析 hook |
| `src/components/ChatWindow.tsx` | ✅ 对话框主容器 + SSE 事件处理 |
| `src/components/MessageBubble.tsx` | ✅ 用户/AI/系统/数据/策略 全消息类型渲染 |
| `src/components/DataCard.tsx` | ✅ 赛道/天气/排位/练习赛 4 种卡片 |
| `src/components/AgentThinkingBlock.tsx` | ✅ 可折叠推理过程 |
| `src/components/StrategyCard.tsx` | ✅ 策略建议高亮卡片 |
| `src/App.tsx` | ✅ 整体布局 |
| `src/main.tsx` | ✅ Tailwind CSS v4 入口 |

构建验证：`npm run build` → TypeScript + Vite 通过，0 错误。

### Phase 5: RL 轨迹 + 策略对比 ✅ 已完成

| 文件 | 状态 |
|------|------|
| `backend/harness/orchestrator.py` `_run_post_race` | ✅ 赛后复盘：加载实际结果 + 查找预测轨迹 + 对比 + 计算奖励 |
| `backend/harness/orchestrator.py` `_compute_reward` | ✅ 奖励规则：冠军匹配 +1.0, 策略匹配 +0.5, 名次偏差惩罚 |
| `backend/main.py` `GET /api/traces` | ✅ 轨迹列表 + 准确率统计 |
| `frontend/src/types/index.ts` `ComparisonData` | ✅ 对比数据类型 |
| `frontend/src/components/ComparisonCard.tsx` | ✅ 赛后复盘卡片：实际排名表 + Agent 预测对比 + RL 奖励 |
| `frontend/src/components/MessageBubble.tsx` | ✅ 支持 comparison 消息渲染 |
| `frontend/src/components/ChatWindow.tsx` | ✅ 支持 comparison_card 事件 |

**RL 闭环完整流程**：
1. 赛前分析 → 自动保存轨迹（state + agent_outputs + prediction）
2. 赛后复盘 → 加载实际结果 → 查找轨迹 → 计算 reward → 回填轨迹
3. `GET /api/traces` → 查看所有轨迹和准确率

---

## 全部完成 ✅

所有 5 个 Phase 均已完成。项目总计 **44 个文件**。

### 启动方式

```bash
# 1. 安装 Python 虚拟环境（首次）
cd Agent
python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt

# 2. 启动后端
./run_backend.sh

# 3. 启动前端（新终端）
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`，输入 F1 策略问题即可。
- 后端 API: `http://localhost:8000`
- 前端开发服务器: `http://localhost:5173`（自动代理 `/api` 到后端）
- 验证健康检查: `curl http://localhost:8000/api/health` → `{"status":"ok"}`

每个 Phase 的验证在对应章节已说明。整体端到端验证：

1. 启动后端：`cd backend && uvicorn main:app --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 浏览器打开 `localhost:5173`
4. 在输入框输入："分析一下2024摩纳哥大奖赛的轮胎策略"
5. 观察：
   - 系统识别消息出现（"识别为：赛前策略分析 · 摩纳哥大奖赛"）
   - 数据卡片逐一加载（赛道信息、天气、排位赛结果、练习赛分析）
   - Agent 气泡逐个出现并流式输出推理过程
   - 策略卡片展示最终建议
6. 追问："如果安全车在第15圈出现呢？"
7. 观察 Agent 基于上下文给出新的分析
8. curl 验证：`curl -N -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"prompt":"分析2024摩纳哥站策略","history":[]}'`