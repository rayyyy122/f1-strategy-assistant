"""Agent 编排器——根据 Intent 调度 Agent 团队，流式推送 SSE 事件。"""

import asyncio
import json
import time
from typing import AsyncGenerator

from .router import route_intent
from .logger import get_logger
from . import guardrails
from ..agents.race_context import create_agent as create_race_context
from ..agents.tire_strategist import create_agent as create_tire_strategist
from ..agents.competitor_analyst import create_agent as create_competitor_analyst
from ..agents.synthesis import create_agent as create_synthesis
from ..agents.intake import create_agent as create_intake
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
    "intake": create_intake,
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

    # 快照 token tracker 起始值（用于本次请求的增量统计）
    from .logger import token_tracker
    start_input = token_tracker.total_input
    start_output = token_tracker.total_output

    # ---- Step 0: 路由 ----
    intent = await route_intent(prompt, history)
    logger.info(f"Router → mode={intent.mode}, season={intent.season}, round={intent.round}")

    routing_msg = _routing_message(intent)
    yield {"type": "routing", "mode": intent.mode, "message": routing_msg}

    memory.working.intent = intent.model_dump()

    # ---- 根据 mode 分发 ----
    # 使用 drain helper 在 Agent 执行时同步抽取 event_queue 的流式事件
    try:
        if intent.mode == "pre_race":
            # pre_race 之前先过 intake gate：缺字段就反问、不进策略分析
            async for event in _drain_with(
                _run_intake_then_pre_race(intent, prompt, history, event_queue, memory),
                event_queue,
            ):
                yield event

        elif intent.mode == "post_race":
            async for event in _drain_with(_run_post_race(intent, prompt, event_queue, memory), event_queue):
                yield event

        elif intent.mode == "follow_up":
            async for event in _drain_with(_run_follow_up(intent, prompt, event_queue, memory), event_queue):
                yield event

        elif intent.mode == "track_info":
            async for event in _drain_with(_run_quick(prompt, event_queue, memory, force_tool=True, history=history), event_queue):
                yield event

        else:
            # quick_question 或未知 mode：不强制工具
            async for event in _drain_with(_run_quick(prompt, event_queue, memory, force_tool=False, history=history), event_queue):
                yield event
    except Exception as e:
        logger.error(f"Agent 执行失败: {e}", exc_info=True)
        yield {"type": "error", "message": f"分析失败: {e}"}

    # ---- 最终事件 ----
    elapsed = round(time.time() - total_start, 1)
    usage = {
        "input_tokens": token_tracker.total_input - start_input,
        "output_tokens": token_tracker.total_output - start_output,
    }
    logger.info(f"完成，耗时 {elapsed}s, tokens={usage}")

    yield {"type": "complete", "elapsed_s": elapsed, "usage": usage}


async def _compute_next_missing(extracted: dict) -> dict | None:
    """按 season→race→team→driver 顺序找第一个缺失字段，调工具生成 options。

    返回 None 表示 4 字段齐全。
    """
    season = extracted.get("season")
    round_num = extracted.get("round")
    team = extracted.get("team")
    driver = extracted.get("driver")

    # ---- Step 1: season ----
    if not season:
        from .time_context import current_season
        cs = current_season()
        years = list(range(cs, cs - 9, -1))  # 当前赛季回退 8 年
        options = [
            {"value": str(y), "label": f"{y} 赛季{'（当前）' if y == cs else ''}"}
            for y in years
        ]
        options.append({"value": "other", "label": "更早赛季（请直接输入年份）"})
        return {
            "field": "season",
            "label": "赛季",
            "prompt_hint": "你想分析哪个赛季的比赛？",
            "options": options,
        }

    try:
        season_int = int(season)
    except (ValueError, TypeError):
        return {
            "field": "season",
            "label": "赛季",
            "prompt_hint": f"无法识别赛季 '{season}'，请重新选择",
            "options": [],
        }

    # ---- Step 2: race（round + race_name）----
    if not round_num:
        from ..tools.team_driver_tools import _lookup_race
        sched_result = await _lookup_race(season_int, "")
        schedule = sched_result.get("schedule", [])
        options = [
            {
                "value": str(r["round"]),
                "label": _race_label_cn(r),
            }
            for r in schedule
        ]
        return {
            "field": "race",
            "label": "比赛",
            "prompt_hint": f"{season_int} 赛季你想分析哪一站？",
            "options": options,
        }

    # ---- Step 3: team ----
    if not team:
        from ..tools.team_driver_tools import _list_season_teams
        result = await _list_season_teams(season_int)
        teams = result.get("teams", [])
        options = [
            {"value": t["value"], "label": _team_label_cn(t["value"])}
            for t in teams
        ]
        return {
            "field": "team",
            "label": "车队",
            "prompt_hint": "针对哪个车队的策略？",
            "options": options,
        }

    # ---- Step 4: driver ----
    if not driver:
        from ..tools.team_driver_tools import _lookup_team
        result = await _lookup_team(team, season_int)
        drivers = result.get("drivers", []) if result.get("found") else []
        options = [
            {"value": d, "label": _driver_label_cn(d)}
            for d in drivers
        ]
        return {
            "field": "driver",
            "label": "车手",
            "prompt_hint": f"{team} 的哪位车手？",
            "options": options,
        }

    return None  # 4 字段齐全


# ---- 中文显示映射（label 用，value 仍是规范英文名）----

_TEAM_CN: dict[str, str] = {
    "Red Bull Racing": "红牛", "Ferrari": "法拉利", "Mercedes": "梅赛德斯",
    "McLaren": "迈凯伦", "Aston Martin": "阿斯顿马丁", "Alpine": "阿尔派",
    "Williams": "威廉姆斯", "Racing Bulls": "小红牛", "RB": "小红牛",
    "Kick Sauber": "索伯", "Sauber": "索伯", "Audi": "奥迪",
    "Haas": "哈斯", "Cadillac": "凯迪拉克",
    # 历史车队
    "Renault": "雷诺", "Force India": "印度力量", "Lotus": "莲花",
    "Toro Rosso": "红牛二队", "AlphaTauri": "阿尔法塔利", "Alfa Romeo": "阿尔法罗密欧",
    "Caterham": "卡特汉姆", "Manor": "马诺", "HRT": "HRT",
    "Marussia": "玛鲁西亚",
}

_DRIVER_CN: dict[str, str] = {
    "Max Verstappen": "维斯塔潘", "Sergio Perez": "佩雷兹",
    "Charles Leclerc": "勒克莱尔", "Carlos Sainz": "塞恩斯",
    "Lewis Hamilton": "汉密尔顿", "George Russell": "拉塞尔",
    "Lando Norris": "诺里斯", "Oscar Piastri": "皮亚斯特里",
    "Fernando Alonso": "阿隆索", "Lance Stroll": "斯特罗尔",
    "Pierre Gasly": "加斯利", "Esteban Ocon": "奥康",
    "Alexander Albon": "阿尔本", "Logan Sargeant": "萨金特",
    "Daniel Ricciardo": "里卡多", "Yuki Tsunoda": "角田裕毅",
    "Valtteri Bottas": "博塔斯", "Zhou Guanyu": "周冠宇",
    "Kevin Magnussen": "马格努森", "Nico Hulkenberg": "霍肯伯格",
    "Andrea Kimi Antonelli": "安东内利", "Franco Colapinto": "科拉平托",
    "Liam Lawson": "劳森", "Isack Hadjar": "哈贾尔",
    "Gabriel Bortoleto": "博尔托莱托", "Oliver Bearman": "贝尔曼",
    "Arvid Lindblad": "林德布拉德",
}

_RACE_CN: dict[str, str] = {
    "Bahrain": "巴林", "Saudi Arabian": "沙特", "Australian": "澳大利亚",
    "Japanese": "日本", "Chinese": "中国", "Miami": "迈阿密",
    "Emilia Romagna": "伊莫拉", "Monaco": "摩纳哥", "Canadian": "加拿大",
    "Spanish": "西班牙", "Austrian": "奥地利", "British": "英国",
    "Hungarian": "匈牙利", "Belgian": "比利时", "Dutch": "荷兰",
    "Italian": "意大利", "Azerbaijan": "阿塞拜疆", "Singapore": "新加坡",
    "United States": "美国", "Mexico City": "墨西哥城", "Brazilian": "巴西",
    "Las Vegas": "拉斯维加斯", "Qatar": "卡塔尔", "Abu Dhabi": "阿布扎比",
    "Barcelona": "巴塞罗那",
}


def _race_label_cn(race: dict) -> str:
    """生成赛事中文标签：'摩纳哥大奖赛 (Monaco GP, 第8站, 2026-06-07)'"""
    name = race.get("race_name", "")
    short = name.replace(" Grand Prix", "").strip()
    cn = _RACE_CN.get(short, short)
    rnd = race.get("round", "?")
    date = race.get("date", "")
    en_short = f"{short} GP" if short else name
    suffix = f"第{rnd}站"
    if date:
        suffix += f", {date}"
    return f"{cn}大奖赛 ({en_short}, {suffix})" if cn != short else f"{en_short} (第{rnd}站, {date})"


def _team_label_cn(team_en: str) -> str:
    """生成车队中文标签：'法拉利 (Ferrari)'"""
    cn = _TEAM_CN.get(team_en)
    return f"{cn} ({team_en})" if cn else team_en


def _driver_label_cn(driver_en: str) -> str:
    """生成车手中文标签：'勒克莱尔 (Charles Leclerc)'"""
    cn = _DRIVER_CN.get(driver_en)
    return f"{cn} ({driver_en})" if cn else driver_en


async def _run_intake_then_pre_race(
    intent: Intent,
    prompt: str,
    history: list[dict],
    event_queue: asyncio.Queue,
    memory: MemoryManager,
) -> AsyncGenerator[dict, None]:
    """先跑 intake agent 校验必填字段，齐了才进 _run_pre_race；缺了就反问。"""
    yield {"type": "agent_start", "agent": "intake"}

    intake_agent = AGENT_FACTORIES["intake"]()
    intake_context = {
        "task": (
            "判断用户是否提供了 pre_race 策略分析所需的 4 个字段（season/round/team/driver）。"
            "按顺序逐一检查，只输出第一个缺失字段的选项。齐了就 ready=true。仅输出 JSON。"
        ),
        "prompt": prompt,
        "history": history,
        "current_intent": {
            "season": intent.season,
            "round": intent.round,
        },
    }
    intake_output = await intake_agent.run(intake_context, None, force_first_tool_call=False)
    yield {"type": "agent_complete", "agent": "intake", "output": intake_output.data}

    data = intake_output.data or {}
    extracted = data.get("extracted") or {}

    # 用 router 已提取的字段做兜底（避免 LLM 漏写）
    if not extracted.get("season") and intent.season:
        extracted["season"] = intent.season
    if not extracted.get("round") and intent.round:
        extracted["round"] = intent.round

    # 代码权威判定 — 不依赖 LLM 的 ready/missing 字段
    next_missing = await _compute_next_missing(extracted)

    if next_missing is not None:
        logger.info(f"Intake gate: 缺失字段 ['{next_missing['field']}'], 不进 pre_race")
        yield {
            "type": "clarification_needed",
            "extracted": extracted,
            "missing": [next_missing],
            "message": next_missing.get("prompt_hint", "我需要补充几个信息才能制定策略"),
        }
        return

    # 把 intake 提取的字段填回 intent
    if extracted.get("season"):
        intent.season = int(extracted["season"])
    if extracted.get("round"):
        intent.round = int(extracted["round"])
    intent.team = extracted.get("team")
    intent.driver = extracted.get("driver")
    intent.race_name = extracted.get("race_name")
    memory.working.intent = intent.model_dump()
    logger.info(
        f"Intake gate 通过：season={intent.season}, round={intent.round}, "
        f"team={intent.team}, driver={intent.driver}"
    )

    # 继续完整 pre_race 流程
    async for event in _run_pre_race(intent, prompt, event_queue, memory):
        yield event


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
    yield {"type": "agent_start", "agent": "race_context", "intermediate": True}
    race_agent = AGENT_FACTORIES["race_context"]()
    target_focus = ""
    if intent.team and intent.driver:
        target_focus = f" 重点针对 {intent.team} 车队的 {intent.driver}。"
    elif intent.team:
        target_focus = f" 重点针对 {intent.team} 车队。"
    elif intent.driver:
        target_focus = f" 重点针对车手 {intent.driver}。"

    race_context = {
        "task": (
            f"分析 {season} 赛季第 {round_num} 站比赛。{target_focus}"
            "请以 JSON 输出（结构化模式），输出会被下游 Agent 解析。"
        ),
        "race_data": race_data,
        "prompt": prompt,
        "target": {"team": intent.team, "driver": intent.driver},
    }
    rc_output = await race_agent.run(race_context, event_queue, force_first_tool_call=True)
    memory.working.set_agent_output("race_context", rc_output)
    yield {"type": "agent_complete", "agent": "race_context", "output": rc_output.data}
    logger.info(f"Race Context 完成")

    # Step 3: Tire + Competitor 并行
    yield {"type": "agent_start", "agent": "tire_strategist", "intermediate": True}
    yield {"type": "agent_start", "agent": "competitor_analyst", "intermediate": True}

    tire_agent = AGENT_FACTORIES["tire_strategist"]()
    comp_agent = AGENT_FACTORIES["competitor_analyst"]()

    context_for_parallel = {
        "task": f"分析 {season} 赛季第 {round_num} 站比赛的策略。{target_focus}",
        "race_data": race_data,
        "upstream_outputs": {"race_context": rc_output},
        "prompt": prompt,
        "target": {"team": intent.team, "driver": intent.driver},
    }

    tire_task = tire_agent.run(context_for_parallel, event_queue)
    comp_task = comp_agent.run(context_for_parallel, event_queue)

    tire_output, comp_output = await asyncio.gather(tire_task, comp_task)

    memory.working.set_agent_output("tire_strategist", tire_output)
    memory.working.set_agent_output("competitor_analyst", comp_output)

    yield {"type": "agent_complete", "agent": "tire_strategist", "output": tire_output.data}
    yield {"type": "agent_complete", "agent": "competitor_analyst", "output": comp_output.data}
    logger.info(f"Tire + Competitor 并行完成")

    # guardrails: 轮胎策略
    tire_warnings = guardrails.validate_tire_strategy(tire_output.data or {})
    if tire_warnings:
        logger.warning(f"Guardrails [tire_strategist] {len(tire_warnings)} 条警告: {'; '.join(tire_warnings[:3])}")
        yield {"type": "guardrails_warning", "agent": "tire_strategist", "warnings": tire_warnings}

    # Step 4: Synthesis
    yield {"type": "agent_start", "agent": "synthesis"}
    synth_agent = AGENT_FACTORIES["synthesis"]()
    synth_context = {
        "task": f"基于以下三个分析，给出 {season} 赛季第 {round_num} 站的最终策略建议。{target_focus}",
        "upstream_outputs": {
            "race_context": rc_output,
            "tire_strategist": tire_output,
            "competitor_analyst": comp_output,
        },
        "prompt": prompt,
        "target": {"team": intent.team, "driver": intent.driver},
    }
    synth_output = await synth_agent.run(synth_context, event_queue)
    memory.working.set_agent_output("synthesis", synth_output)
    memory.working.final_strategy = synth_output.data

    yield {"type": "agent_complete", "agent": "synthesis", "output": synth_output.data}
    yield {"type": "strategy_card", "strategy": synth_output.data}
    logger.info(f"Synthesis 完成")

    # guardrails: 综合策略
    synth_warnings = guardrails.validate_synthesis(synth_output.data or {})
    if synth_warnings:
        logger.warning(f"Guardrails [synthesis] {len(synth_warnings)} 条警告: {'; '.join(synth_warnings[:3])}")
        yield {"type": "guardrails_warning", "agent": "synthesis", "warnings": synth_warnings}

    # Step 5: 保存轨迹
    state = {
        "season": season,
        "round": round_num,
        "race_data": race_data,
        "prompt": prompt,
        "team": intent.team,
        "driver": intent.driver,
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
    logger.info(f"_run_post_race 开始: season={season}, round={round_num}")

    if season is None or round_num is None:
        yield {"type": "error", "message": "请指定比赛。例如：'复盘2024摩纳哥大奖赛'"}
        return

    yield {"type": "progress", "step": "loading", "message": f"正在加载 {season} R{round_num} 实际比赛结果..."}

    # 加载实际结果
    from ..tools.strategy_tools import _load_actual_race_result

    try:
        actual = await _load_actual_race_result(season, round_num)
    except Exception as e:
        logger.error(f"_load_actual_race_result 异常: {e}", exc_info=True)
        yield {"type": "error", "message": f"加载比赛结果异常: {e}"}
        return

    if "error" in actual:
        logger.warning(f"加载比赛结果失败: {actual['error']}")
        yield {"type": "error", "message": actual["error"]}
        return

    results = actual.get("results", [])
    logger.info(f"成功加载 {season} R{round_num} 比赛结果: {len(results)} 位车手")
    yield {"type": "progress", "step": "done", "message": f"已加载 {len(results)} 位车手的成绩"}

    # 查找已有的预测轨迹
    from ..memory.trace_store import list_traces, load_trace
    traces = list_traces(season)
    matching = [t for t in traces if t.get("round") == round_num]

    if matching:
        trace = load_trace(matching[0]["trace_id"])
        prediction = trace.get("final_prediction", {}) if trace else {}
        trace_id = matching[0]["trace_id"]
        logger.info(f"找到历史预测: {trace_id}")
    else:
        prediction = {}
        trace_id = None
        logger.info(f"未找到 {season} R{round_num} 的历史预测")

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
        target_driver = (trace.get("state") or {}).get("driver", "") if trace else ""
        reward = _compute_reward(prediction, actual, target_driver=target_driver)
        from ..memory.trace_store import backfill_outcome
        backfill_outcome(trace_id, actual, reward)
        comparison["reward"] = reward
        comparison["trace_id"] = trace_id

    yield {"type": "comparison_card", "comparison": comparison}

    # 生成文本总结（无论是否有预测都给用户一个文字回答）
    yield {"type": "agent_start", "agent": "synthesis"}
    summary_agent = AGENT_FACTORIES["synthesis"]()
    if prediction:
        task = (
            f"用户复盘 {season} 赛季第 {round_num} 站比赛。\n\n"
            f"已加载实际结果（前 5 名）:\n"
            + "\n".join(f"- P{r['position']} {r['driver']}" for r in results[:5])
            + "\n\n"
            f"Agent 之前的预测:\n{json.dumps(prediction, ensure_ascii=False, indent=2)}\n\n"
            "请简要复盘：预测中正确的部分、错误的部分、关键差异原因。用中文回答，200字以内。"
        )
    else:
        task = (
            f"用户复盘 {season} 赛季第 {round_num} 站比赛。\n\n"
            f"实际结果（前 5 名）:\n"
            + "\n".join(f"- P{r['position']} {r['driver']}" for r in results[:5])
            + "\n\n"
            "提示：系统中没有这场比赛的历史 Agent 预测可供对比。\n"
            "请简要介绍这场比赛的实际结果亮点，并建议用户先进行赛前预测再来复盘。"
            "用中文回答，200字以内。"
        )
    summary_context = {"task": task, "prompt": prompt}
    summary_output = await summary_agent.run(summary_context, event_queue)
    memory.working.set_agent_output("synthesis", summary_output)
    yield {"type": "agent_complete", "agent": "synthesis", "output": summary_output.data}

    logger.info(f"Post-race 复盘完成: {season} R{round_num}")


def _compute_reward(prediction: dict, actual: dict, target_driver: str = "") -> float:
    """4 维度奖励规则（对比对象为预测的目标车手）：

    冠军预测正确  +1.0（预测目标车手 P1 完赛，且其确实夺冠）
    策略类型匹配  +0.5（停站次数与目标车手实际策略一致）
    进站窗口匹配  +0.3（实际进站每命中窗口一次额外 +0.1，上限 0.5）
    名次偏差惩罚  -0.2 × |预测名次 - 目标车手实际名次|（下限 -1.0）

    若无法在实际结果中匹配到目标车手（如轨迹里是中文名），
    回退为与冠军对比（与历史行为一致）。
    """
    import re

    reward = 0.0
    pred_strategy_text = prediction.get("recommended_strategy", "") or ""
    pred_position_raw = str(prediction.get("predicted_position", "") or "")

    results = actual.get("results", [])
    strategies = actual.get("strategies", {})
    if not results:
        return 0.0

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z]", "", (s or "").lower())

    # ---- 解析预测名次（兼容 "P2（最佳P1，最差P4）" 等格式）----
    m = re.search(r"P(\d+)", pred_position_raw)
    pred_pos = int(m.group(1)) if m else 0

    # ---- 定位对比对象：目标车手，匹配不到则回退到冠军 ----
    target_entry = None
    if target_driver:
        norm_target = _norm(target_driver)
        if norm_target:
            target_entry = next(
                (r for r in results if _norm(str(r.get("driver", ""))) == norm_target),
                None,
            )
    if target_entry is None:
        target_entry = results[0]  # 回退：与冠军对比

    target_code = target_entry.get("driver_code", "")
    target_actual_pos = target_entry.get("position", 99)

    # ---- 1. 冠军预测 +1.0（目标车手确实是冠军才算）----
    if pred_pos == 1 and target_entry is results[0]:
        reward += 1.0

    # ---- 2. 策略类型匹配 +0.5（与目标车手实际策略对比）----
    pred_stop_type = ""
    if "一停" in pred_strategy_text:
        pred_stop_type = "一停"
    elif "二停" in pred_strategy_text:
        pred_stop_type = "二停"
    elif "三停" in pred_strategy_text:
        pred_stop_type = "三停"

    target_strategy = strategies.get(target_code) if target_code and strategies else None
    if target_strategy and pred_stop_type:
        if target_strategy.get("strategy") == pred_stop_type:
            reward += 0.5

    # ---- 3. 进站窗口匹配 +0.3~0.5（兼容 dict 格式的多停窗口）----
    pit_window_value = prediction.get("pit_window", "")
    window_texts = (
        list(pit_window_value.values()) if isinstance(pit_window_value, dict) else [pit_window_value]
    )
    pit_windows = [w for w in (_parse_pit_window(t) for t in window_texts) if w]

    if pit_windows and target_strategy:
        pit_laps = target_strategy.get("pit_laps", [])
        hits = sum(
            1 for lap in pit_laps
            if any(start <= lap <= end for start, end in pit_windows)
        )
        if hits > 0:
            reward += min(0.3 + 0.1 * hits, 0.5)

    # ---- 4. 名次偏差惩罚（与目标车手实际名次对比）----
    if pred_pos > 0 and isinstance(target_actual_pos, int) and 1 <= target_actual_pos <= 20:
        delta = abs(pred_pos - target_actual_pos)
        reward += max(-1.0, -0.2 * delta)

    return round(reward, 2)


def _parse_pit_window(text: str) -> tuple[int, int] | None:
    """从中文 pit window 文本中提取 (start, end) 圈数。

    Examples:
        "第20-26圈"  → (20, 26)
        "第15圈"     → (15, 15)
        "第30-35"    → (30, 35)
    """
    import re

    # 处理 None 或非字符串输入
    if text is None:
        return None

    # 转换为字符串
    text = str(text).strip()

    if not text or not isinstance(text, str):
        return None

    match = re.search(r"(\d+)\s*[-–—到至]\s*(\d+)", text)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    match = re.search(r"(\d+)", text)
    if match:
        lap = int(match.group(1))
        return (lap, lap)
    return None


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


async def _run_quick(prompt, event_queue, memory, force_tool: bool = False, history: list[dict] | None = None):
    """快速回答——单 Agent。

    Args:
        force_tool: True 表示问的是具体赛道（track_info），强制 Agent 先调用工具；
                   False 表示通用 F1 知识问答（quick_question），Agent 自由决定是否调工具。
        history: 前端传入的最近 N 轮对话历史，用于保持上下文（如"帮我搜索"指代上一轮话题）。
    """
    yield {"type": "agent_start", "agent": "race_context"}
    agent = AGENT_FACTORIES["race_context"]()
    if force_tool:
        task = (
            "用户在询问具体赛道或当前赛季的赛事信息。按 IRON RULE 判断："
            "提到具体赛道名（如「介绍摩纳哥」）→ 规则 A，直接调 get_circuit_profile；"
            "提到「下一场/本周末/上一场」等时效性比赛询问 → 规则 C1，**先调 lookup_race(season, '') 拿赛历**，"
            "按 date 字段对比注入的当前日期找出对应那场，再调 get_circuit_profile 拿赛道详情。"
            "禁止根据训练记忆猜测哪场是下一场——必须基于工具数据。"
            "用清晰的中文 Markdown 回答（不要 JSON）。"
        )
    else:
        task = (
            "用户在问 F1 知识。按 IRON RULE 判断："
            "定义/规则/概念 → 规则 B 直接答；"
            "「下一场/本周末」类赛历问题 → 规则 C1，先调 lookup_race 再 get_circuit_profile；"
            "「积分榜/规则变化/转会动态」类非赛历时效问题 → 规则 C2 调 web_search；"
            "如果之前轮对话已经提到具体话题且用户说「帮我搜索」「就搜这个」，请结合上文话题构造搜索词，不要要求用户重复说明。"
            "用清晰的中文 Markdown 回答，不要使用 JSON 格式。"
        )
    context = {"task": task, "prompt": prompt, "history": history or []}
    output = await agent.run(context, event_queue, force_first_tool_call=force_tool)
    memory.working.set_agent_output("race_context", output)
    yield {"type": "agent_complete", "agent": "race_context", "output": output.data}


_END_SENTINEL = {"__end__": True}


async def _drain_with(inner_gen, event_queue: asyncio.Queue):
    """并发消费 inner_gen 的 yield 和 event_queue 中的流式事件。

    把 inner 改造成往同一个 queue 投递（与 BaseAgent 共用），
    统一以 queue 为驱动，按时间顺序发到 SSE 流。
    任何 inner 抛出的异常会在主循环中重新抛出，不再静默吞掉。
    """
    producer_exc: list[BaseException] = []

    async def producer():
        try:
            async for ev in inner_gen:
                await event_queue.put(ev)
        except BaseException as e:
            producer_exc.append(e)
            logger.error(f"_drain_with producer 异常: {e}", exc_info=True)
        finally:
            await event_queue.put(_END_SENTINEL)

    task = asyncio.create_task(producer())
    try:
        while True:
            ev = await event_queue.get()
            if ev is _END_SENTINEL:
                # 把队列中残留事件全部排出
                while not event_queue.empty():
                    extra = event_queue.get_nowait()
                    if extra is not _END_SENTINEL:
                        yield extra
                # 如果 producer 抛过异常，重新抛出
                if producer_exc:
                    raise producer_exc[0]
                return
            yield ev
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, BaseException):
                pass


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


def _load_practice_data_sync(season: int, round_num: int) -> tuple[dict, dict]:
    """同步加载练习赛天气 + 长距离数据（放入 worker 线程运行，避免阻塞事件循环）。"""
    from ..data import fastf1_client

    weather = {}
    longruns = {}
    for st in ["FP1", "FP2", "FP3"]:
        try:
            session = fastf1_client.load_session(season, round_num, st)
            weather[st] = fastf1_client.get_weather_data(session)
            longruns[st] = fastf1_client.get_practice_longruns(session)
        except Exception:
            continue
    return weather, longruns


async def _load_race_data(season: int, round_num: int) -> dict:
    """加载比赛数据（赛道 + 天气 + 排位 + 长距离）。"""
    from ..data import jolpica_client

    data = {}

    # 赛道信息
    try:
        circuit = await jolpica_client.get_circuit_info(season, round_num)
        data["circuit"] = circuit
    except Exception as e:
        logger.warning(f"赛道信息加载失败: {e}")

    # 天气 + 练习赛长距离（FastF1 为同步阻塞 IO，放入线程，保证超时可以生效）
    weather, longruns = await asyncio.to_thread(_load_practice_data_sync, season, round_num)
    if weather:
        data["weather"] = weather
    if longruns:
        data["practice_longruns"] = longruns

    # 排位赛
    try:
        qualifying = await jolpica_client.get_qualifying_results(season, round_num)
        data["qualifying"] = qualifying[:10] if qualifying else []
    except Exception as e:
        logger.warning(f"排位赛数据加载失败: {e}")

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