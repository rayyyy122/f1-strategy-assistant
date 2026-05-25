"""意图路由器 — 关键词 + LLM 双层分类。"""

import json
import asyncio
import logging

from ..llm_client import get_client
from ..models.schemas import Intent
from ..config import LLM_MODEL

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """你是 F1 策略助手的意图路由器。根据用户输入分类到以下模式，输出严格的 JSON。

模式：
- pre_race: 分析某场比赛的赛前策略。关键词：分析策略、预测、进站、轮胎、谁能赢、赛前。
- post_race: 赛后对比/复盘。关键词：复盘、对比、验证、实际结果。
- track_info: 查询赛道信息。关键词：赛道特点、是什么赛道、历史。
- quick_question: 一般F1知识问答（不需要具体比赛数据）。
- follow_up: 追问上一轮的结果。

常见赛道的 round 编号(2024): 1=巴林, 2=沙特, 3=澳大利亚, 4=日本, 5=中国, 6=迈阿密, 7=伊莫拉, 8=摩纳哥, 9=加拿大, 10=西班牙, 11=奥地利, 12=英国, 13=匈牙利, 14=比利时, 15=荷兰, 16=意大利, 17=阿塞拜疆, 18=新加坡, 19=美国, 20=墨西哥, 21=巴西, 22=拉斯维加斯, 23=卡塔尔, 24=阿布扎比

输出格式: {"mode": "pre_race", "season": 2024, "round": 8}"""

# 关键词 → mode 快速匹配表
_KEYWORD_MODE_MAP = [
    (["分析", "策略", "预测", "进站", "轮胎", "夺冠", "谁能赢", "赛前", "排位"], "pre_race"),
    (["复盘", "对比", "验证", "实际结果", "vs预测", "回顾"], "post_race"),
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
        logger.info(f"Router (keyword) → mode={best_mode}, season={season}, round={round_num}")
        return Intent(mode=best_mode, season=season, round=round_num, params={})

    # Step 2: LLM 分类
    messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}]
    if history:
        for msg in history[-4:]:
            messages.append({"role": msg.get("role", "user"), "content": str(msg.get("content", ""))})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=LLM_MODEL,
            max_tokens=128,
            messages=messages,
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

    return Intent(
        mode=data.get("mode", "quick_question"),
        season=data.get("season"),
        round=data.get("round"),
        params={k: v for k, v in data.items() if k not in ("mode", "season", "round")},
    )


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