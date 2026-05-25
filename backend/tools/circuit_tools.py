"""赛道信息工具。"""

import asyncio
from .registry import registry
from ..data import jolpica_client
from ..models.schemas import TrackInfo

# ---- 赛道知识库 ----

_TRACK_PROFILES: dict[str, TrackInfo] = {
    "monaco": TrackInfo(
        circuit_name="Circuit de Monaco",
        locality="Monte Carlo",
        country="Monaco",
        length_km=3.337,
        corners=19,
        drs_zones=1,
        overtaking_difficulty="极难",
        lap_record="1:12.909 (Lewis Hamilton, 2021)",
        first_gp_year=1950,
    ),
    "silverstone": TrackInfo(
        circuit_name="Silverstone Circuit",
        locality="Silverstone",
        country="UK",
        length_km=5.891,
        corners=18,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:27.097 (Max Verstappen, 2020)",
        first_gp_year=1950,
    ),
    "spa": TrackInfo(
        circuit_name="Circuit de Spa-Francorchamps",
        locality="Spa",
        country="Belgium",
        length_km=7.004,
        corners=19,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:46.286 (Valtteri Bottas, 2018)",
        first_gp_year=1950,
    ),
    "monza": TrackInfo(
        circuit_name="Autodromo Nazionale di Monza",
        locality="Monza",
        country="Italy",
        length_km=5.793,
        corners=11,
        drs_zones=2,
        overtaking_difficulty="容易",
        lap_record="1:21.046 (Rubens Barrichello, 2004)",
        first_gp_year=1950,
    ),
    "suzuka": TrackInfo(
        circuit_name="Suzuka International Racing Course",
        locality="Suzuka",
        country="Japan",
        length_km=5.807,
        corners=18,
        drs_zones=1,
        overtaking_difficulty="困难",
        lap_record="1:30.983 (Lewis Hamilton, 2019)",
        first_gp_year=1987,
    ),
}


async def _get_circuit_profile(track_name: str) -> dict | None:
    """获取赛道基本信息（从知识库或 API）。

    包含赛道长度、弯道数、DRS 区数量、超车难度评级、历史杆位夺冠率等。
    """
    key = track_name.lower().strip()
    if key in _TRACK_PROFILES:
        return _TRACK_PROFILES[key].model_dump()
    # 在知识库中近似匹配
    for k, v in _TRACK_PROFILES.items():
        if key in k or k in key:
            return v.model_dump()
    return None


async def _get_historical_strategies(track_name: str, years: int = 5) -> dict:
    """获取某赛道的历史策略模式。

    返回近N年的进站统计：一停/二停比例、常见轮胎配方、平均进站窗口。
    """
    key = track_name.lower().strip()
    # 模拟数据（后续可用 FastF1 真实数据替换）
    strategies = {
        "monaco": {
            "typical_strategy": "一停",
            "one_stop_pct": 80,
            "two_stop_pct": 15,
            "common_compounds": ["SOFT→HARD", "MEDIUM→HARD"],
            "avg_pit_window": "第18-26圈",
            "safety_car_probability": 0.35,
            "pole_to_win_pct": 80,
        },
        "silverstone": {
            "typical_strategy": "一停或二停均可",
            "one_stop_pct": 55,
            "two_stop_pct": 40,
            "common_compounds": ["MEDIUM→HARD", "SOFT→MEDIUM→HARD"],
            "avg_pit_window": "第15-25圈",
            "safety_car_probability": 0.25,
            "pole_to_win_pct": 55,
        },
        "default": {
            "typical_strategy": "一停",
            "one_stop_pct": 60,
            "two_stop_pct": 35,
            "common_compounds": ["MEDIUM→HARD"],
            "avg_pit_window": "第15-25圈",
            "safety_car_probability": 0.20,
            "pole_to_win_pct": 60,
        },
    }
    for k in strategies:
        if k in key:
            return strategies[k]
    return strategies["default"]


# 注册工具
registry.register(
    name="get_circuit_profile",
    description="获取赛道基本信息：长度、弯道数、DRS区数量、超车难度评级。输入赛道名称（如 'monaco'、'silverstone'）。",
    func=_get_circuit_profile,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_name": {
                "type": "string",
                "description": "赛道名称，如 'monaco', 'silverstone', 'spa', 'monza', 'suzuka'",
            },
        },
        "required": ["track_name"],
    },
    agents=["race_context"],
)

registry.register(
    name="get_historical_strategies",
    description="获取某赛道近N年的历史进站策略模式：一停/二停比例、常见轮胎配方、平均进站窗口、安全车概率、杆位夺冠率。",
    func=_get_historical_strategies,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_name": {"type": "string", "description": "赛道名称"},
            "years": {"type": "integer", "description": "统计年份数，默认 5"},
        },
        "required": ["track_name"],
    },
    agents=["race_context"],
)