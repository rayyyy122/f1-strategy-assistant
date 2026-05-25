"""练习赛/排位赛数据工具。"""

from .registry import registry
from ..data import fastf1_client, jolpica_client


async def _get_practice_longruns(year: int, round_num: int) -> dict:
    """从练习赛中提取所有车手的长距离数据。

    遍历 FP1/FP2/FP3，提取连续多圈同一轮胎的数据段，
    计算各配方的平均圈速。

    Args:
        year: 赛季年份
        round_num: 比赛轮次

    Returns:
        {
            "FP2": {
                "VER": [{"compound": "MEDIUM", "laps": 8, "avg_time": 92.3}, ...],
                ...
            },
            ...
        }
    """
    result = {}
    for session_type in ["FP1", "FP2", "FP3"]:
        try:
            session = fastf1_client.load_session(year, round_num, session_type)
            result[session_type] = fastf1_client.get_practice_longruns(session)
        except Exception:
            continue
    return result


async def _get_qualifying_results(year: int, round_num: int) -> list[dict]:
    """获取排位赛结果（前10名）。

    Returns:
        [{"position": 1, "driver": "Charles Leclerc", "team": "Ferrari",
          "q3_time": "1:10.270", "gap_to_pole": 0}, ...]
    """
    raw = await jolpica_client.get_qualifying_results(year, round_num)
    results = []
    for r in raw[:10]:
        pos = int(r["position"])
        driver = f"{r['Driver']['givenName']} {r['Driver']['familyName']}"
        team = r["Constructor"]["name"]
        q3 = r.get("Q3", r.get("Q2", r.get("Q1", "")))

        # 计算与杆位的差距
        pole_time = None
        if raw and raw[0].get("Q3"):
            pole_time = _parse_time(raw[0]["Q3"])

        gap = 0
        if pos > 1 and pole_time and q3:
            t = _parse_time(q3)
            if t:
                gap = round(t - pole_time, 3)

        results.append({
            "position": pos,
            "driver": driver,
            "team": team,
            "q3_time": q3,
            "gap_to_pole": gap,
        })
    return results


def _parse_time(time_str: str) -> float | None:
    """将 "1:10.270" 格式的圈速转换为秒数。"""
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(time_str)
    except (ValueError, AttributeError):
        return None


async def _get_driver_form(driver_name: str, year: int) -> dict:
    """获取车手近期表现趋势。

    从积分榜和排位赛结果分析车手状态。
    """
    standings = await jolpica_client.get_driver_standings(year)
    for s in standings:
        full_name = f"{s['Driver']['givenName']} {s['Driver']['familyName']}"
        if driver_name.lower() in full_name.lower():
            return {
                "driver": full_name,
                "position": int(s["position"]),
                "points": float(s["points"]),
                "wins": int(s["wins"]),
                "team": s["Constructors"][0]["name"],
                "status": _form_status(int(s["position"])),
            }
    return {"error": f"未找到车手 {driver_name} 的积分数据"}


def _form_status(position: int) -> str:
    if position <= 3:
        return "争冠梯队"
    elif position <= 6:
        return "上游稳定"
    elif position <= 12:
        return "中游竞争"
    else:
        return "下游"


# 注册工具
registry.register(
    name="get_practice_longruns",
    description="从FP1/FP2/FP3练习赛中提取所有车手的长距离数据：各配方的连续圈数和平均圈速。至少5圈连续使用同一轮胎才计入。用于计算轮胎退化率。",
    func=_get_practice_longruns,
    parameters_schema={
        "type": "object",
        "properties": {
            "year": {"type": "integer", "description": "赛季年份"},
            "round_num": {"type": "integer", "description": "比赛轮次"},
        },
        "required": ["year", "round_num"],
    },
    agents=["tire_strategist", "competitor_analyst"],
)

registry.register(
    name="get_qualifying_results",
    description="获取排位赛前10名结果：车手、车队、排位圈速、与杆位差距。",
    func=_get_qualifying_results,
    parameters_schema={
        "type": "object",
        "properties": {
            "year": {"type": "integer", "description": "赛季年份"},
            "round_num": {"type": "integer", "description": "比赛轮次"},
        },
        "required": ["year", "round_num"],
    },
    agents=["competitor_analyst", "race_context"],
)

registry.register(
    name="get_driver_form",
    description="获取车手在当前赛季的积分排名、胜场、所属车队和状态评估。",
    func=_get_driver_form,
    parameters_schema={
        "type": "object",
        "properties": {
            "driver_name": {"type": "string", "description": "车手全名，如 'Charles Leclerc'"},
            "year": {"type": "integer", "description": "赛季年份"},
        },
        "required": ["driver_name", "year"],
    },
    agents=["competitor_analyst"],
)