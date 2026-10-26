"""FastF1 数据加载封装。"""

import fastf1
from fastf1.core import Session
from ..config import FASTF1_CACHE_DIR

# 启用 FastF1 内置缓存
fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR))


def load_session(year: int, round_num: int, session_type: str) -> Session:
    """加载指定比赛周末的某一节。

    Args:
        year: 赛季年份
        round_num: 比赛轮次（1-based）
        session_type: 节类型 — "FP1", "FP2", "FP3", "Q", "R"

    Returns:
        fastf1.core.Session 对象
    """
    session = fastf1.get_session(year, round_num, session_type)
    session.load()
    return session


def get_lap_times(session: Session) -> "pd.DataFrame":
    """获取所有车手圈速数据（每圈每位车手一行）。"""
    return session.laps


def get_tire_data(session: Session, driver: str = None):
    """获取轮胎配方和使用圈数。

    Args:
        session: 已加载的 session
        driver: 车手代号（如 "LEC"），None 返回所有车手

    Returns:
        DataFrame: 每圈的轮胎信息（compound, tire_age, lap_number）
    """
    laps = session.laps
    if driver:
        laps = laps[laps["Driver"] == driver]
    return laps[["Driver", "LapNumber", "Compound", "TyreLife", "LapTime"]]


def get_weather_data(session: Session) -> dict:
    """获取该节的平均天气数据。

    Returns:
        {
            "air_temp": float,       # 气温 °C
            "track_temp": float,     # 赛道温度 °C
            "humidity": float,       # 湿度 %
            "rainfall": bool,        # 是否降雨
            "wind_speed": float      # 风速 km/h
        }
    """
    weather = session.weather_data
    return {
        "air_temp": round(weather["AirTemp"].mean(), 1),
        "track_temp": round(weather["TrackTemp"].mean(), 1),
        "humidity": round(weather["Humidity"].mean(), 1),
        "rainfall": bool(weather["Rainfall"].any()),
        "wind_speed": round(weather["WindSpeed"].mean(), 1),
    }


def get_practice_longruns(session: Session, min_laps: int = 5) -> dict[str, list[dict]]:
    """从练习赛中提取长距离数据（连续多圈同一轮胎）。

    Args:
        session: 练习赛 session (FP1/FP2/FP3)
        min_laps: 最少连续圈数才算长距离

    Returns:
        {
            "VER": [{"compound": "MEDIUM", "laps": 8, "avg_time": 92.3}, ...],
            ...
        }
    """
    laps = session.laps
    result: dict[str, list[dict]] = {}

    for driver in laps["Driver"].unique():
        driver_laps = laps[laps["Driver"] == driver].sort_values("LapNumber")
        runs = []
        current_compound = None
        run_laps = []

        for _, lap in driver_laps.iterrows():
            compound = str(lap["Compound"])
            if compound != current_compound:
                if len(run_laps) >= min_laps:
                    times = [l["LapTime"].total_seconds() for l in run_laps]
                    runs.append({
                        "compound": current_compound,
                        "laps": len(run_laps),
                        "avg_time": round(sum(times) / len(times), 3),
                    })
                current_compound = compound
                run_laps = []
            run_laps.append(lap)

        if len(run_laps) >= min_laps:
            times = [l["LapTime"].total_seconds() for l in run_laps]
            runs.append({
                "compound": current_compound,
                "laps": len(run_laps),
                "avg_time": round(sum(times) / len(times), 3),
            })

        if runs:
            result[driver] = runs

    return result