"""赛道信息工具。"""

from .registry import registry
from ..models.schemas import TrackInfo

# ---- 完整赛道知识库（2024-2026 F1 赛历）----
# 数据来源：F1 官方资料 + 维基百科。新赛道（如 Madrid）字段保守填充。

_TRACK_PROFILES: dict[str, TrackInfo] = {
    "bahrain": TrackInfo(
        circuit_name="Bahrain International Circuit",
        locality="Sakhir",
        country="Bahrain",
        length_km=5.412,
        corners=15,
        drs_zones=3,
        overtaking_difficulty="中等",
        lap_record="1:31.447 (Pedro de la Rosa, 2005)",
        first_gp_year=2004,
    ),
    "saudi_arabia": TrackInfo(
        circuit_name="Jeddah Corniche Circuit",
        locality="Jeddah",
        country="Saudi Arabia",
        length_km=6.174,
        corners=27,
        drs_zones=3,
        overtaking_difficulty="困难",
        lap_record="1:30.734 (Lewis Hamilton, 2021)",
        first_gp_year=2021,
    ),
    "australia": TrackInfo(
        circuit_name="Albert Park Circuit",
        locality="Melbourne",
        country="Australia",
        length_km=5.278,
        corners=14,
        drs_zones=4,
        overtaking_difficulty="中等",
        lap_record="1:19.813 (Charles Leclerc, 2024)",
        first_gp_year=1996,
    ),
    "japan": TrackInfo(
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
    "china": TrackInfo(
        circuit_name="Shanghai International Circuit",
        locality="Shanghai",
        country="China",
        length_km=5.451,
        corners=16,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:32.238 (Michael Schumacher, 2004)",
        first_gp_year=2004,
    ),
    "miami": TrackInfo(
        circuit_name="Miami International Autodrome",
        locality="Miami Gardens",
        country="USA",
        length_km=5.412,
        corners=19,
        drs_zones=3,
        overtaking_difficulty="中等",
        lap_record="1:29.708 (Max Verstappen, 2023)",
        first_gp_year=2022,
    ),
    "imola": TrackInfo(
        circuit_name="Autodromo Enzo e Dino Ferrari",
        locality="Imola",
        country="Italy",
        length_km=4.909,
        corners=19,
        drs_zones=2,
        overtaking_difficulty="极难",
        lap_record="1:15.484 (Lewis Hamilton, 2020)",
        first_gp_year=1980,
    ),
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
    "canada": TrackInfo(
        circuit_name="Circuit Gilles Villeneuve",
        locality="Montreal",
        country="Canada",
        length_km=4.361,
        corners=14,
        drs_zones=3,
        overtaking_difficulty="中等",
        lap_record="1:13.078 (Valtteri Bottas, 2019)",
        first_gp_year=1978,
    ),
    "spain": TrackInfo(
        circuit_name="Circuit de Barcelona-Catalunya",
        locality="Montmeló",
        country="Spain",
        length_km=4.657,
        corners=14,
        drs_zones=2,
        overtaking_difficulty="困难",
        lap_record="1:16.330 (Max Verstappen, 2023)",
        first_gp_year=1991,
    ),
    "austria": TrackInfo(
        circuit_name="Red Bull Ring",
        locality="Spielberg",
        country="Austria",
        length_km=4.318,
        corners=10,
        drs_zones=3,
        overtaking_difficulty="容易",
        lap_record="1:05.619 (Carlos Sainz, 2020)",
        first_gp_year=1970,
    ),
    "britain": TrackInfo(
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
    "hungary": TrackInfo(
        circuit_name="Hungaroring",
        locality="Mogyoród",
        country="Hungary",
        length_km=4.381,
        corners=14,
        drs_zones=1,
        overtaking_difficulty="困难",
        lap_record="1:16.627 (Lewis Hamilton, 2020)",
        first_gp_year=1986,
    ),
    "belgium": TrackInfo(
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
    "netherlands": TrackInfo(
        circuit_name="Circuit Zandvoort",
        locality="Zandvoort",
        country="Netherlands",
        length_km=4.259,
        corners=14,
        drs_zones=2,
        overtaking_difficulty="困难",
        lap_record="1:11.097 (Lewis Hamilton, 2021)",
        first_gp_year=1952,
    ),
    "italy": TrackInfo(
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
    "azerbaijan": TrackInfo(
        circuit_name="Baku City Circuit",
        locality="Baku",
        country="Azerbaijan",
        length_km=6.003,
        corners=20,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:43.009 (Charles Leclerc, 2019)",
        first_gp_year=2016,
    ),
    "singapore": TrackInfo(
        circuit_name="Marina Bay Street Circuit",
        locality="Singapore",
        country="Singapore",
        length_km=4.940,
        corners=19,
        drs_zones=3,
        overtaking_difficulty="困难",
        lap_record="1:35.867 (Lewis Hamilton, 2023)",
        first_gp_year=2008,
    ),
    "usa": TrackInfo(
        circuit_name="Circuit of the Americas",
        locality="Austin, Texas",
        country="USA",
        length_km=5.513,
        corners=20,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:36.169 (Charles Leclerc, 2019)",
        first_gp_year=2012,
    ),
    "mexico": TrackInfo(
        circuit_name="Autódromo Hermanos Rodríguez",
        locality="Mexico City",
        country="Mexico",
        length_km=4.304,
        corners=17,
        drs_zones=3,
        overtaking_difficulty="中等",
        lap_record="1:17.774 (Valtteri Bottas, 2021)",
        first_gp_year=1963,
    ),
    "brazil": TrackInfo(
        circuit_name="Autódromo José Carlos Pace (Interlagos)",
        locality="São Paulo",
        country="Brazil",
        length_km=4.309,
        corners=15,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:10.540 (Valtteri Bottas, 2018)",
        first_gp_year=1973,
    ),
    "las_vegas": TrackInfo(
        circuit_name="Las Vegas Strip Circuit",
        locality="Las Vegas, Nevada",
        country="USA",
        length_km=6.201,
        corners=17,
        drs_zones=2,
        overtaking_difficulty="容易",
        lap_record="1:34.876 (Oscar Piastri, 2024)",
        first_gp_year=2023,
    ),
    "qatar": TrackInfo(
        circuit_name="Lusail International Circuit",
        locality="Lusail",
        country="Qatar",
        length_km=5.419,
        corners=16,
        drs_zones=1,
        overtaking_difficulty="困难",
        lap_record="1:24.319 (Lando Norris, 2024)",
        first_gp_year=2021,
    ),
    "abu_dhabi": TrackInfo(
        circuit_name="Yas Marina Circuit",
        locality="Abu Dhabi",
        country="UAE",
        length_km=5.281,
        corners=16,
        drs_zones=2,
        overtaking_difficulty="中等",
        lap_record="1:26.103 (Max Verstappen, 2021)",
        first_gp_year=2009,
    ),
    "madrid": TrackInfo(
        circuit_name="Madring (Madrid Circuit, IFEMA)",
        locality="Madrid",
        country="Spain",
        length_km=5.474,
        corners=22,
        drs_zones=2,
        overtaking_difficulty="未知（新赛道）",
        lap_record="尚无（2026 首次启用）",
        first_gp_year=2026,
    ),
}

# 别名表 — 中文名 / 通用别名 → 知识库 key
_TRACK_ALIASES: dict[str, str] = {
    # Bahrain
    "巴林": "bahrain", "sakhir": "bahrain", "萨基尔": "bahrain",
    # Saudi
    "沙特": "saudi_arabia", "沙特阿拉伯": "saudi_arabia", "吉达": "saudi_arabia", "jeddah": "saudi_arabia",
    "saudi": "saudi_arabia",
    # Australia
    "澳大利亚": "australia", "澳洲": "australia", "墨尔本": "australia",
    "melbourne": "australia", "albert park": "australia",
    # Japan
    "日本": "japan", "铃鹿": "japan", "suzuka": "japan",
    # China
    "中国": "china", "上海": "china", "shanghai": "china",
    # Miami
    "迈阿密": "miami",
    # Imola
    "伊莫拉": "imola", "圣马力诺": "imola",
    # Monaco
    "摩纳哥": "monaco", "蒙特卡洛": "monaco", "monte carlo": "monaco",
    # Canada
    "加拿大": "canada", "蒙特利尔": "canada", "montreal": "canada",
    # Spain
    "西班牙": "spain", "巴塞罗那": "spain", "加泰罗尼亚": "spain",
    "barcelona": "spain", "catalunya": "spain",
    # Austria
    "奥地利": "austria", "红牛环": "austria", "spielberg": "austria", "red bull ring": "austria",
    # UK
    "英国": "britain", "uk": "britain", "silverstone": "britain", "银石": "britain",
    "great britain": "britain",
    # Hungary
    "匈牙利": "hungary", "布达佩斯": "hungary", "hungaroring": "hungary",
    # Belgium
    "比利时": "belgium", "斯帕": "belgium", "spa": "belgium", "spa-francorchamps": "belgium",
    # Netherlands
    "荷兰": "netherlands", "赞德沃特": "netherlands", "zandvoort": "netherlands",
    # Italy / Monza
    "意大利": "italy", "蒙扎": "italy", "monza": "italy",
    # Azerbaijan
    "阿塞拜疆": "azerbaijan", "巴库": "azerbaijan", "baku": "azerbaijan",
    # Singapore
    "新加坡": "singapore", "滨海湾": "singapore", "marina bay": "singapore",
    # USA - Austin
    "美国": "usa", "奥斯汀": "usa", "austin": "usa", "cota": "usa",
    # Mexico
    "墨西哥": "mexico", "墨西哥城": "mexico", "rodriguez": "mexico",
    # Brazil
    "巴西": "brazil", "圣保罗": "brazil", "interlagos": "brazil",
    # Las Vegas
    "拉斯维加斯": "las_vegas", "vegas": "las_vegas",
    # Qatar
    "卡塔尔": "qatar", "卢塞尔": "qatar", "lusail": "qatar",
    # Abu Dhabi
    "阿布扎比": "abu_dhabi", "亚斯码头": "abu_dhabi", "yas marina": "abu_dhabi",
    # Madrid (2026 新)
    "马德里": "madrid", "madring": "madrid", "ifema": "madrid",
}


def _resolve_track_key(track_name: str) -> str | None:
    """把任意输入（中英文名、别名）解析为知识库 key。"""
    if not track_name:
        return None
    key = track_name.lower().strip()
    if key in _TRACK_PROFILES:
        return key
    if key in _TRACK_ALIASES:
        return _TRACK_ALIASES[key]
    # 模糊匹配：别名表
    for alias, k in _TRACK_ALIASES.items():
        if alias in key or key in alias:
            return k
    return None


async def _get_circuit_profile(track_name: str) -> dict:
    """获取赛道基本信息（从知识库）。

    返回字段含 `found` 标志：
    - found=True 时附带完整赛道数据
    - found=False 时返回提示信息，Agent 必须如实告知用户
    """
    key = _resolve_track_key(track_name)
    if key is None:
        return {
            "found": False,
            "requested_track": track_name,
            "message": (
                f"系统知识库中暂无 '{track_name}' 的赛道资料。"
                "请明确告知用户：无法提供该赛道的具体技术参数。"
                "不要编造数据。"
            ),
            "available_tracks": sorted(_TRACK_PROFILES.keys()),
        }

    profile = _TRACK_PROFILES[key].model_dump()
    profile["found"] = True
    profile["resolved_key"] = key
    return profile


# ---- 历史策略模式 ----

_HISTORICAL_STRATEGIES: dict[str, dict] = {
    "monaco": {
        "typical_strategy": "一停",
        "one_stop_pct": 80, "two_stop_pct": 15,
        "common_compounds": ["SOFT→HARD", "MEDIUM→HARD"],
        "avg_pit_window": "第18-26圈",
        "safety_car_probability": 0.55,
        "pole_to_win_pct": 80,
    },
    "britain": {
        "typical_strategy": "一停或二停均可",
        "one_stop_pct": 55, "two_stop_pct": 40,
        "common_compounds": ["MEDIUM→HARD", "SOFT→MEDIUM→HARD"],
        "avg_pit_window": "第15-25圈",
        "safety_car_probability": 0.25,
        "pole_to_win_pct": 55,
    },
    "spain": {
        "typical_strategy": "二停为主",
        "one_stop_pct": 30, "two_stop_pct": 65,
        "common_compounds": ["MEDIUM→HARD→HARD", "SOFT→HARD→HARD"],
        "avg_pit_window": "第20-30圈",
        "safety_car_probability": 0.20,
        "pole_to_win_pct": 60,
    },
    "belgium": {
        "typical_strategy": "一停",
        "one_stop_pct": 70, "two_stop_pct": 25,
        "common_compounds": ["MEDIUM→HARD"],
        "avg_pit_window": "第14-22圈",
        "safety_car_probability": 0.35,
        "pole_to_win_pct": 45,
    },
    "italy": {
        "typical_strategy": "一停",
        "one_stop_pct": 85, "two_stop_pct": 10,
        "common_compounds": ["MEDIUM→HARD", "SOFT→HARD"],
        "avg_pit_window": "第18-26圈",
        "safety_car_probability": 0.20,
        "pole_to_win_pct": 60,
    },
    "singapore": {
        "typical_strategy": "一停或二停",
        "one_stop_pct": 50, "two_stop_pct": 45,
        "common_compounds": ["MEDIUM→HARD", "SOFT→MEDIUM→HARD"],
        "avg_pit_window": "第20-30圈",
        "safety_car_probability": 0.75,
        "pole_to_win_pct": 70,
    },
    "japan": {
        "typical_strategy": "一停或二停",
        "one_stop_pct": 55, "two_stop_pct": 40,
        "common_compounds": ["MEDIUM→HARD"],
        "avg_pit_window": "第15-23圈",
        "safety_car_probability": 0.25,
        "pole_to_win_pct": 55,
    },
    "bahrain": {
        "typical_strategy": "二停",
        "one_stop_pct": 20, "two_stop_pct": 70,
        "common_compounds": ["SOFT→HARD→HARD", "MEDIUM→HARD→HARD"],
        "avg_pit_window": "第14-22圈",
        "safety_car_probability": 0.30,
        "pole_to_win_pct": 50,
    },
}

_DEFAULT_STRATEGY = {
    "typical_strategy": "一停",
    "one_stop_pct": 60, "two_stop_pct": 35,
    "common_compounds": ["MEDIUM→HARD"],
    "avg_pit_window": "第15-25圈",
    "safety_car_probability": 0.25,
    "pole_to_win_pct": 55,
}


async def _get_historical_strategies(track_name: str, years: int = 5) -> dict:
    """获取某赛道的历史策略模式。"""
    key = _resolve_track_key(track_name)
    if key is None:
        return {
            "found": False,
            "requested_track": track_name,
            "message": f"系统暂无 '{track_name}' 的历史策略数据。不要编造。",
        }

    data = dict(_HISTORICAL_STRATEGIES.get(key, _DEFAULT_STRATEGY))
    data["found"] = True
    data["resolved_key"] = key
    data["source"] = "specific" if key in _HISTORICAL_STRATEGIES else "default_template"
    return data


# 注册工具
registry.register(
    name="get_circuit_profile",
    description=(
        "获取赛道基本信息：长度、弯道数、DRS区数量、超车难度评级、首办年份。"
        "覆盖 2024-2026 F1 赛历全部赛道（含 2026 首次启用的 Madrid）。"
        "支持中英文名、别名。如果返回 found=false，说明系统无此赛道数据，请如实告知用户。"
    ),
    func=_get_circuit_profile,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_name": {
                "type": "string",
                "description": (
                    "赛道名称，支持中英文：如 'monaco'/'摩纳哥', 'silverstone'/'英国'/'银石', "
                    "'spain'/'西班牙'/'巴塞罗那', 'madrid'/'马德里' 等"
                ),
            },
        },
        "required": ["track_name"],
    },
    agents=["race_context"],
)

registry.register(
    name="get_historical_strategies",
    description=(
        "获取某赛道近N年的历史进站策略模式：一停/二停比例、常见轮胎配方、"
        "平均进站窗口、安全车概率、杆位夺冠率。"
        "如果返回 found=false，说明系统无此赛道数据，请如实告知用户。"
    ),
    func=_get_historical_strategies,
    parameters_schema={
        "type": "object",
        "properties": {
            "track_name": {"type": "string", "description": "赛道名称（中英文）"},
            "years": {"type": "integer", "description": "统计年份数，默认 5"},
        },
        "required": ["track_name"],
    },
    agents=["race_context"],
)