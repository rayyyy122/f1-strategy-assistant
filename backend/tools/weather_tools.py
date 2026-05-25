"""天气数据工具。"""

import asyncio
from .registry import registry
from ..data import fastf1_client
from ..config import FASTF1_CACHE_DIR


async def _get_weather_forecast(year: int, round_num: int) -> dict:
    """获取比赛周末的天气预测。

    优先从 FastF1 加载实际天气数据（练习赛期间的天气），
    作为正赛天气的参考。
    """
    # 加载练习赛天气数据作为参考
    weather_data = {}
    for session_type in ["FP1", "FP2", "FP3"]:
        try:
            session = fastf1_client.load_session(year, round_num, session_type)
            weather_data[session_type] = fastf1_client.get_weather_data(session)
        except Exception:
            continue

    if not weather_data:
        return {"error": f"无法加载 {year} R{round_num} 的天气数据"}

    # 取各练习赛的平均值
    sessions = list(weather_data.values())
    n = len(sessions)

    return {
        "source": f"基于 {', '.join(weather_data.keys())} 的实际天气数据",
        "air_temp_c": round(sum(s["air_temp"] for s in sessions) / n, 1),
        "track_temp_c": round(sum(s["track_temp"] for s in sessions) / n, 1),
        "humidity_pct": round(sum(s["humidity"] for s in sessions) / n, 1),
        "rainfall_detected": any(s["rainfall"] for s in sessions),
        "wind_speed_kmh": round(sum(s["wind_speed"] for s in sessions) / n, 1),
        "forecast_note": (
            "雨天概率较高，建议关注降雨对策略的影响"
            if any(s["rainfall"] for s in sessions)
            else "天气晴朗，无降雨风险"
        ),
    }


registry.register(
    name="get_weather_forecast",
    description="获取F1比赛周末的天气数据：气温、赛道温度、湿度、降雨情况、风速。数据来源为练习赛期间的实际天气测量。",
    func=_get_weather_forecast,
    parameters_schema={
        "type": "object",
        "properties": {
            "year": {"type": "integer", "description": "赛季年份"},
            "round_num": {"type": "integer", "description": "比赛轮次"},
        },
        "required": ["year", "round_num"],
    },
    agents=["race_context"],
)