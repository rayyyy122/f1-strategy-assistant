"""意图路由器 — 关键词 + LLM 双层分类。"""

import json
import asyncio
import logging

from ..llm_client import get_client
from ..models.schemas import Intent
from ..config import LLM_MODEL
from .time_context import current_time_prefix, current_season
from .retry import retry_async

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """你是 F1 策略助手的意图路由器。根据用户输入分类到以下模式，输出严格的 JSON。

模式：
- pre_race: 分析某场比赛的赛前策略。关键词：分析策略、预测、进站、轮胎、谁能赢、赛前。
- post_race: 赛后对比/复盘。关键词：复盘、对比、验证、实际结果、真实结果、符合、是否准确、对不对、和实际、正赛结果。
- track_info: 查询赛道信息。关键词：赛道特点、是什么赛道、历史。
- quick_question: 一般F1知识问答（不需要具体比赛数据）。
- follow_up: 追问上一轮的"如果场景"或细节追问（如"如果下雨呢"、"为什么选硬胎"）。

规则：
- **post_race 优先识别**：用户提及"实际结果"、"真实结果"、"符合"、"对不对"、"是否准确"、"和实际比"等词，且对话历史里有过 pre_race 策略分析 → 必定是 post_race。本轮 season/round 从对话历史里的上一轮 pre_race 继承。
- "那实际结果如何？符合这个策略建议吗"、"实际比赛和这个建议一致吗"、"对不对" 类追问 → **post_race**（不是 follow_up，也不是 quick_question）。
- follow_up 仅用于"如果X情况下""为什么这样"等假设/解释性追问，不是真实结果对比。
- 用户提及"下一场/这一场/本周/最近一场"等当前赛季事件时，season 取系统注入的当前赛季。
- 用户没有提及任何年份时，不要猜测往年（如 2024）；季节字段保留为 null 或填当前赛季。
- round 编号每年不同，依据用户指定的赛道名 + 年份决定，不能假设固定映射。

输出格式: {"mode": "post_race", "season": 2024, "round": 8}"""

# 关键词 → mode 快速匹配表
_KEYWORD_MODE_MAP = [
    (["分析", "策略", "预测", "进站", "轮胎", "夺冠", "谁能赢", "赛前", "排位"], "pre_race"),
    (["复盘", "对比", "验证", "实际结果", "vs预测", "回顾", "真实结果", "正赛结果", "符合", "是否准确", "对不对", "和实际"], "post_race"),
    (["赛道", "特点", "是什么", "历史"], "track_info"),
]


async def route_intent(prompt: str, history: list[dict] | None = None) -> Intent:
    """分类用户 prompt — 先用关键词，再用 LLM。"""
    client = get_client()
    prompt_lower = prompt.lower()

    # Step 1: 关键词启发式匹配
    scores = {}
    for keywords, mode in _KEYWORD_MODE_MAP:
        scores[mode] = sum(1 for kw in keywords if kw in prompt_lower)

    best_mode = max(scores, key=scores.get) if scores else ""
    best_score = scores.get(best_mode, 0)

    # 如果关键词匹配明确(>=2个词命中)，直接返回，节省 LLM 调用
    if best_score >= 2:
        season, round_num = _extract_season_round(prompt_lower)
        # post_race / follow_up：本轮没年份+轮次时优先从 history 继承
        if best_mode in ("post_race", "follow_up") and history:
            if season is None or round_num is None:
                hist_season, hist_round = _extract_season_round_from_history(history)
                if season is None and hist_season is not None:
                    season = hist_season
                if round_num is None and hist_round is not None:
                    round_num = hist_round
        # pre_race 留给 intake agent 处理缺失字段（含赛季），不要自动填当前赛季
        if season is None and best_mode in ("post_race", "follow_up"):
            season = current_season()
        logger.info(f"Router (keyword) → mode={best_mode}, season={season}, round={round_num}")
        return Intent(mode=best_mode, season=season, round=round_num, params={})

    # Step 2: LLM 分类
    messages = [{"role": "system", "content": current_time_prefix() + "\n\n" + ROUTER_SYSTEM_PROMPT}]
    if history:
        for msg in history[-4:]:
            messages.append({"role": msg.get("role", "user"), "content": str(msg.get("content", ""))})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await retry_async(
            lambda: asyncio.to_thread(
                client.chat.completions.create,
                model=LLM_MODEL,
                max_tokens=128,
                messages=messages,
            ),
            name="router_llm",
            attempts=2,
            base_delay=0.5,
            max_delay=2.0,
            timeout=30.0,
        )
        text = response.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"Router LLM 调用失败: {e}, 回退到 quick_question")
        return Intent(mode="quick_question")

    # 提取 JSON
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "{" in text:
        start = text.index("{")
        end = text.rindex("}") + 1
        text = text[start:end]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Router JSON 解析失败: {text[:200]}")
        return Intent(mode="quick_question")

    logger.info(f"Router (LLM) → mode={data.get('mode')}, season={data.get('season')}, round={data.get('round')}")

    mode = data.get("mode", "quick_question")
    season = data.get("season")
    round_num = data.get("round")

    import re
    user_specified_year = bool(re.search(r"20\d{2}", prompt))

    # post_race / follow_up：本轮没年份时优先从 history 继承（上一轮 pre_race 的 season+round）
    if mode in ("post_race", "follow_up") and history:
        hist_season, hist_round = _extract_season_round_from_history(history)
        if not user_specified_year and hist_season is not None:
            if season is None or season != hist_season:
                if season is not None:
                    logger.info(f"Router: {mode} LLM season={season}，但 history 上一轮是 {hist_season}，使用 history")
                season = hist_season
        if round_num is None and hist_round is not None:
            round_num = hist_round
            logger.info(f"Router: {mode} 从 history 继承 round={round_num}")

    # 防御：用户 prompt 没有显式年份且 history 也未提供 → LLM 倾向猜训练截止时间。
    # pre_race 模式下留给 intake agent 处理（不要自动填当前赛季），
    # 其他需要比赛数据的模式统一按当前赛季兜底。
    if not user_specified_year:
        if mode in ("post_race", "follow_up") and season is None:
            season = current_season()
            logger.info(f"Router: {mode} season 仍为空，兜底为当前赛季 {season}")
        elif mode == "pre_race":
            # pre_race 由 intake agent 负责反问缺失字段（含赛季），不要自动填
            if season is not None:
                logger.info(f"Router: pre_race LLM 自动填了 season={season}，但用户未指定年份，回置为 None 交给 intake")
            season = None

    return Intent(
        mode=mode,
        season=season,
        round=round_num,
        params={k: v for k, v in data.items() if k not in ("mode", "season", "round")},
    )


def _extract_season_round_from_history(history: list[dict]) -> tuple[int | None, int | None]:
    """扫描历史中最近一条 user 消息，提取 season + round（用于 post_race/follow_up 上下文继承）。"""
    import re
    track_map = {
        "巴林": 1, "沙特": 2, "澳大利亚": 3, "澳洲": 3, "墨尔本": 3,
        "日本": 4, "铃鹿": 4, "中国": 5, "上海": 5,
        "迈阿密": 6, "伊莫拉": 7, "摩纳哥": 8, "monaco": 8,
        "加拿大": 9, "蒙特利尔": 9, "西班牙": 10, "巴塞罗那": 10,
        "奥地利": 11, "英国": 12, "银石": 12, "silverstone": 12,
        "匈牙利": 13, "比利时": 14, "斯帕": 14, "spa": 14,
        "荷兰": 15, "意大利": 16, "蒙扎": 16, "monza": 16,
        "阿塞拜疆": 17, "巴库": 17, "新加坡": 18,
        "美国": 19, "奥斯汀": 19, "墨西哥": 20, "巴西": 21, "圣保罗": 21,
        "拉斯维加斯": 22, "卡塔尔": 23, "阿布扎比": 24,
    }
    season = None
    round_num = None
    # 倒序扫历史，找最早能补全 season+round 的来源
    for msg in reversed(history):
        if msg.get("role") not in ("user", "assistant", "agent"):
            continue
        content = str(msg.get("content", "")).lower()
        if season is None:
            m = re.search(r"(20\d{2})", content)
            if m:
                season = int(m.group(1))
        if round_num is None:
            for name, r in track_map.items():
                if name in content:
                    round_num = r
                    break
        if season is not None and round_num is not None:
            break
    return season, round_num


def _extract_season_round(prompt_lower: str) -> tuple[int | None, int | None]:
    """从 prompt 中提取 season 和 round。"""
    import re

    # 匹配年份
    season = None
    year_match = re.search(r"(20\d{2})", prompt_lower)
    if year_match:
        season = int(year_match.group(1))

    # 赛道名 → round 映射
    track_map = {
        "巴林": 1, "沙特": 2, "澳大利亚": 3, "澳洲": 3,
        "日本": 4, "中国": 5, "上海": 5,
        "迈阿密": 6, "伊莫拉": 7, "摩纳哥": 8, "monaco": 8,
        "加拿大": 9, "西班牙": 10,
        "奥地利": 11, "英国": 12, "银石": 12, "silverstone": 12,
        "匈牙利": 13, "比利时": 14, "斯帕": 14, "spa": 14,
        "荷兰": 15, "意大利": 16, "蒙扎": 16, "monza": 16,
        "阿塞拜疆": 17, "新加坡": 18,
        "美国": 19, "墨西哥": 20, "巴西": 21,
        "拉斯维加斯": 22, "卡塔尔": 23, "阿布扎比": 24,
    }
    round_num = None
    for name, r in track_map.items():
        if name in prompt_lower:
            round_num = r
            break

    return season, round_num