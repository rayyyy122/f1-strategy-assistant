"""Agent 编排器——根据 Intent 调度 Agent 团队，流式推送 SSE 事件。"""

import asyncio
import time
from typing import AsyncGenerator

from .router import route_intent
from .logger import get_logger
from ..agents.race_context import create_agent as create_race_context
from ..agents.tire_strategist import create_agent as create_tire_strategist
from ..agents.competitor_analyst import create_agent as create_competitor_analyst
from ..agents.synthesis import create_agent as create_synthesis
from ..memory.manager import MemoryManager
from ..memory.trace_store import save_trace
from ..models.schemas import Intent

logger = get_logger(__name__)

# Agent 工厂
AGENT_FACTORIES = {
    "race_context": create_race_context,
    "tire_strategist": create_tire_strategist,
    "competitor_analyst": create_competitor_analyst,
    "synthesis": create_synthesis,
}


async def handle_prompt(
    prompt: str,
    history: list[dict] | None = None,
    memory: MemoryManager | None = None,
) -> AsyncGenerator[dict, None]:
    """处理用户 prompt，流式返回 SSE 事件。

    流程：
    1. Router 分类
    2. 根据 mode 加载数据
    3. 调度 Agent 执行
    4. 存入记忆 + 轨迹
    """
    if memory is None:
        memory = MemoryManager()

    history = history or []
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    total_start = time.time()

    # ---- Step 0: 路由 ----
    intent = await route_intent(prompt, history)
    logger.info(f"Router → mode={intent.mode}, season={intent.season}, round={intent.round}")

    routing_msg = _routing_message(intent)
    yield {"type": "routing", "mode": intent.mode, "message": routing_msg}

    memory.working.intent = intent.model_dump()

    # ---- 根据 mode 分发 ----
    try:
        if intent.mode == "pre_race":
            async for event in _run_pre_race(intent, prompt, event_queue, memory):
                yield event

        elif intent.mode == "post_race":
            async for event in _run_post_race(intent, prompt, event_queue, memory):
                yield event

        elif intent.mode == "follow_up":
            async for event in _run_follow_up(intent, prompt, event_queue, memory):
                yield event

        else:
            async for event in _run_quick(prompt, event_queue, memory):
                yield event
    except Exception as e:
        logger.error(f"Agent 执行失败: {e}", exc_info=True)
        yield {"type": "error", "message": f"分析失败: {e}"}

    # ---- 最终事件 ----
    elapsed = round(time.time() - total_start, 1)
    logger.info(f"完成，耗时 {elapsed}s")

    yield {"type": "complete", "elapsed_s": elapsed}


async def _run_pre_race(
    intent: Intent,
    prompt: str,
    event_queue: asyncio.Queue,
    memory: MemoryManager,
) -> AsyncGenerator[dict, None]:
    """赛前策略分析——完整 4 Agent 流程。"""
    season = intent.season
    round_num = intent.round

    if season is None or round_num is None:
        yield {"type": "error", "message": "请指定比赛。例如：'分析2024摩纳哥大奖赛的策略'"}
        return

    # Step 1: 加载数据
    yield {"type": "progress", "step": "loading", "message": f"正在加载 {season} R{round_num} 比赛数据..."}
    race_data = await _load_race_data(season, round_num)
    memory.working.race_data = race_data

    for card in _build_data_cards(race_data):
        yield card

    yield {"type": "progress", "step": "done", "message": "数据加载完成，开始 Agent 分析"}

    # Step 2: Race Context (先跑，为后续 Agent 提供上下文)
    yield {"type": "agent_start", "agent": "race_context"}
    race_agent = AGENT_FACTORIES["race_context"]()
    race_context = {
        "task": f"分析 {season} 赛季第 {round_num} 站比赛",
        "race_data": race_data,
        "prompt": prompt,
    }
    rc_output = await race_agent.run(race_context, event_queue)
    memory.working.set_agent_output("race_context", rc_output)
    yield {"type": "agent_complete", "agent": "race_context", "output": rc_output.data}
    logger.info(f"Race Context 完成")

    # Step 3: Tire + Competitor 并行
    yield {"type": "agent_start", "agent": "tire_strategist"}
    yield {"type": "agent_start", "agent": "competitor_analyst"}

    tire_agent = AGENT_FACTORIES["tire_strategist"]()
    comp_agent = AGENT_FACTORIES["competitor_analyst"]()

    context_for_parallel = {
        "task": f"分析 {season} 赛季第 {round_num} 站比赛的策略",
        "race_data": race_data,
        "upstream_outputs": {"race_context": rc_output},
        "prompt": prompt,
    }

    tire_task = tire_agent.run(context_for_parallel, event_queue)
    comp_task = comp_agent.run(context_for_parallel, event_queue)

    tire_output, comp_output = await asyncio.gather(tire_task, comp_task)

    memory.working.set_agent_output("tire_strategist", tire_output)
    memory.working.set_agent_output("competitor_analyst", comp_output)

    yield {"type": "agent_complete", "agent": "tire_strategist", "output": tire_output.data}
    yield {"type": "agent_complete", "agent": "competitor_analyst", "output": comp_output.data}
    logger.info(f"Tire + Competitor 并行完成")

    # Step 4: Synthesis
    yield {"type": "agent_start", "agent": "synthesis"}
    synth_agent = AGENT_FACTORIES["synthesis"]()
    synth_context = {
        "task": f"基于以下三个分析，给出 {season} 赛季第 {round_num} 站的最终策略建议",
        "upstream_outputs": {
            "race_context": rc_output,
            "tire_strategist": tire_output,
            "competitor_analyst": comp_output,
        },
        "prompt": prompt,
    }
    synth_output = await synth_agent.run(synth_context, event_queue)
    memory.working.set_agent_output("synthesis", synth_output)
    memory.working.final_strategy = synth_output.data

    yield {"type": "agent_complete", "agent": "synthesis", "output": synth_output.data}
    yield {"type": "strategy_card", "strategy": synth_output.data}
    logger.info(f"Synthesis 完成")

    # Step 5: 保存轨迹
    state = {
        "season": season,
        "round": round_num,
        "race_data": race_data,
        "prompt": prompt,
    }
    agent_outputs = {
        name: (out.data if hasattr(out, "data") else out)
        for name, out in memory.working.agent_outputs.items()
    }
    trace_id = save_trace(
        mode="pre_race",
        season=season,
        round_num=round_num,
        prompt=prompt,
        state=state,
        agent_outputs=agent_outputs,
        final_prediction=synth_output.data,
    )
    logger.info(f"轨迹已保存: {trace_id}")


async def _run_post_race(intent, prompt, event_queue, memory):
    """赛后复盘——加载实际结果，对比预测。"""
    season = intent.season
    round_num = intent.round

    if season is None or round_num is None:
        yield {"type": "error", "message": "请指定比赛。例如：'复盘2024摩纳哥大奖赛'"}
        return

    yield {"type": "progress", "step": "loading", "message": f"正在加载 {season} R{round_num} 实际比赛结果..."}

    # 加载实际结果
    from ..data import fastf1_client
    from ..tools.strategy_tools import _load_actual_race_result

    actual = await _load_actual_race_result(season, round_num)
    if "error" in actual:
        yield {"type": "error", "message": actual["error"]}
        return

    yield {"type": "progress", "step": "done", "message": "实际结果加载完成"}

    # 查找已有的预测轨迹
    from ..memory.trace_store import list_traces, load_trace
    traces = list_traces(season)
    matching = [t for t in traces if t.get("round") == round_num]

    if matching:
        trace = load_trace(matching[0]["trace_id"])
        prediction = trace.get("final_prediction", {}) if trace else {}
        trace_id = matching[0]["trace_id"]
    else:
        prediction = {}
        trace_id = None

    # 构建对比数据
    comparison = {
        "season": season,
        "round": round_num,
        "actual": actual,
        "prediction": prediction,
        "has_prediction": bool(prediction),
    }

    # 如果之前有预测，计算奖励并回填
    if trace_id and prediction:
        reward = _compute_reward(prediction, actual)
        from ..memory.trace_store import backfill_outcome
        backfill_outcome(trace_id, actual, reward)
        comparison["reward"] = reward
        comparison["trace_id"] = trace_id

    yield {"type": "comparison_card", "comparison": comparison}
    logger.info(f"Post-race 复盘完成: {season} R{round_num}")


def _compute_reward(prediction: dict, actual: dict) -> float:
    """根据预测和实际结果计算奖励。

    奖励规则：
    - 冠军预测正确: +1.0
    - 策略类型匹配（一停/二停）: +0.5
    - 进站窗口接近实际: +0.3  (如果实际进站在预测窗口内)
    - 完赛名次偏差惩罚: -0.2 * |delta_position|
    """
    reward = 0.0

    pred_strategy = prediction.get("recommended_strategy", "").lower()
    pred_position = prediction.get("predicted_position", "")

    # 策略类型
    if "actual_strategy" in actual:
        actual_strat = actual["actual_strategy"].lower()
        if "一停" in pred_strategy and "一停" in actual_strat:
            reward += 0.5
        elif "二停" in pred_strategy and "二停" in actual_strat:
            reward += 0.5

    # 实际比赛结果中的冠军
    results = actual.get("results", [])
    if results:
        winner = results[0].get("driver", "")
        if pred_position:
            # 名次偏差
            pos_map = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
            pred_pos = pos_map.get(pred_position, 0)
            actual_pos = 1  # winner is P1
            if pred_pos == actual_pos:
                reward += 1.0
            elif pred_pos > 0:
                reward += max(-1.0, 0.5 - 0.2 * abs(pred_pos - actual_pos))

    return round(reward, 2)


async def _run_follow_up(intent, prompt, event_queue, memory):
    """多轮追问——保留上下文，仅运行 Synthesis。"""
    upstream = memory.working.get_agent_outputs()
    if not upstream:
        yield {"type": "error", "message": "没有上下文，请先进行一次完整的策略分析"}
        return

    yield {"type": "agent_start", "agent": "synthesis"}
    synth_agent = AGENT_FACTORIES["synthesis"]()
    synth_context = {
        "task": f"基于之前的分析，回答用户的追问",
        "upstream_outputs": upstream,
        "prompt": prompt,
    }
    synth_output = await synth_agent.run(synth_context, event_queue)
    memory.working.set_agent_output("synthesis", synth_output)

    yield {"type": "agent_complete", "agent": "synthesis", "output": synth_output.data}
    yield {"type": "strategy_card", "strategy": synth_output.data}


async def _run_quick(prompt, event_queue, memory):
    """快速回答——单 Agent。"""
    yield {"type": "agent_start", "agent": "race_context"}
    agent = AGENT_FACTORIES["race_context"]()
    output = await agent.run({"prompt": prompt}, event_queue)
    memory.working.set_agent_output("race_context", output)
    yield {"type": "agent_complete", "agent": "race_context", "output": output.data}


# ---- 辅助函数 ----

def _routing_message(intent: Intent) -> str:
    """生成路由识别消息。"""
    match intent.mode:
        case "pre_race":
            race = f"{intent.season} 赛季"
            if intent.round:
                race += f" 第 {intent.round} 站"
            return f"识别为：赛前策略分析 · {race}"
        case "post_race":
            return "识别为：赛后复盘对比"
        case "track_info":
            return "识别为：赛道信息查询"
        case "quick_question":
            return "识别为：F1 问答"
        case "follow_up":
            return "识别为：追问"
        case _:
            return f"识别为：{intent.mode}"


async def _load_race_data(season: int, round_num: int) -> dict:
    """加载比赛数据（赛道 + 天气）。"""
    from ..data import jolpica_client
    from ..data import fastf1_client

    data = {}

    # 赛道信息
    try:
        circuit = await jolpica_client.get_circuit_info(season, round_num)
        data["circuit"] = circuit
    except Exception as e:
        logger.warning(f"赛道信息加载失败: {e}")

    # 天气（从练习赛）
    weather = {}
    for st in ["FP1", "FP2", "FP3"]:
        try:
            session = fastf1_client.load_session(season, round_num, st)
            weather[st] = fastf1_client.get_weather_data(session)
        except Exception:
            continue
    if weather:
        data["weather"] = weather

    # 排位赛
    try:
        qualifying = await jolpica_client.get_qualifying_results(season, round_num)
        data["qualifying"] = qualifying[:10] if qualifying else []
    except Exception as e:
        logger.warning(f"排位赛数据加载失败: {e}")

    # 练习赛长距离
    longruns = {}
    for st in ["FP1", "FP2", "FP3"]:
        try:
            session = fastf1_client.load_session(season, round_num, st)
            longruns[st] = fastf1_client.get_practice_longruns(session)
        except Exception:
            continue
    if longruns:
        data["practice_longruns"] = longruns

    return data


def _build_data_cards(race_data: dict) -> list[dict]:
    """将比赛数据转换为前端数据卡片事件。"""
    cards = []

    # 赛道卡片
    circuit = race_data.get("circuit", {})
    if circuit:
        cards.append({
            "type": "data_card",
            "card_type": "track",
            "data": {
                "name": circuit.get("circuitName", "未知赛道"),
                "locality": circuit.get("Location", {}).get("locality", ""),
                "country": circuit.get("Location", {}).get("country", ""),
            },
        })

    # 天气卡片
    weather = race_data.get("weather", {})
    if weather:
        # 取最后可用的练习赛天气
        last = list(weather.values())[-1]
        cards.append({
            "type": "data_card",
            "card_type": "weather",
            "data": {
                "air_temp_c": last.get("air_temp"),
                "track_temp_c": last.get("track_temp"),
                "humidity_pct": last.get("humidity"),
                "rainfall": last.get("rainfall", False),
                "wind_speed_kmh": last.get("wind_speed"),
                "sessions": list(weather.keys()),
            },
        })

    # 排位赛卡片
    qualifying = race_data.get("qualifying", [])
    if qualifying:
        results = []
        for r in qualifying[:5]:
            results.append({
                "position": int(r.get("position", 0)),
                "driver": f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
                "team": r.get("Constructor", {}).get("name", ""),
                "q3_time": r.get("Q3", r.get("Q2", r.get("Q1", ""))),
            })
        cards.append({
            "type": "data_card",
            "card_type": "qualifying",
            "data": {"results": results},
        })

    # 练习赛卡片（简化为摘要）
    longruns = race_data.get("practice_longruns", {})
    if longruns:
        recent = list(longruns.values())[-1]  # 取最近的练习赛
        driver_count = len(recent)
        cards.append({
            "type": "data_card",
            "card_type": "practice",
            "data": {
                "session": list(longruns.keys())[-1],
                "drivers_analyzed": driver_count,
                "summary": f"{driver_count} 位车手有长距离数据",
            },
        })

    return cards