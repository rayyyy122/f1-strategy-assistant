"""状态特征提取器 — 从轨迹中提取 RL 训练所需的状态向量。"""

from typing import Any
import re


def extract_state(trace: dict[str, Any]) -> dict[str, Any]:
    """从轨迹中提取标准化状态特征。

    Args:
        trace: 轨迹记录（包含 state 字段）

    Returns:
        标准化的状态特征字典，包含：
        - track_features: 赛道特征
        - weather_features: 天气特征
        - qualifying_features: 排位赛特征
        - longrun_features: 长距离数据特征
    """
    state = trace.get("state", {})
    race_data = state.get("race_data", {})

    # 1. 赛道特征
    track_features = _extract_track_features(race_data.get("circuit", {}))

    # 2. 天气特征
    weather_features = _extract_weather_features(race_data.get("weather", {}))

    # 3. 排位赛特征
    driver_name = state.get("driver", "")
    qualifying_features = _extract_qualifying_features(
        race_data.get("qualifying", []),
        driver_name
    )

    # 4. 长距离数据特征
    longrun_features = _extract_longrun_features(
        race_data.get("practice_longruns", {})
    )

    # 5. 元数据
    meta_features = {
        "season": trace.get("season"),
        "round": trace.get("round"),
        "driver": driver_name,
        "team": state.get("team", ""),
    }

    return {
        "track_features": track_features,
        "weather_features": weather_features,
        "qualifying_features": qualifying_features,
        "longrun_features": longrun_features,
        "meta_features": meta_features,
    }


def _extract_track_features(circuit: dict[str, Any]) -> dict[str, Any]:
    """提取赛道特征。"""
    # 超车难度映射
    overtaking_map = {
        "极难": 0, "困难": 0.3, "中等": 0.6, "容易": 1.0,
        "very hard": 0, "hard": 0.3, "medium": 0.6, "easy": 1.0,
    }

    difficulty = circuit.get("overtaking_difficulty", "中等")
    if isinstance(difficulty, str):
        overtaking_score = overtaking_map.get(difficulty.lower(), 0.6)
    else:
        overtaking_score = 0.6

    return {
        "track_length_km": float(circuit.get("length_km", 0)),
        "corners": int(circuit.get("corners", 0)),
        "drs_zones": len(circuit.get("drs_zones", [])),
        "overtaking_difficulty": overtaking_score,
        "track_type": _classify_track_type(circuit),
    }


def _classify_track_type(circuit: dict[str, Any]) -> str:
    """根据赛道特征分类赛道类型。"""
    length = circuit.get("length_km", 0)
    corners = circuit.get("corners", 0)
    drs_zones = circuit.get("drs_zones", [])
    overtaking = circuit.get("overtaking_difficulty", "中等")

    # 街道赛特征
    circuit_name = circuit.get("circuitName", "").lower()
    if any(x in circuit_name for x in ["monaco", "street", "singapore", "baku", "las vegas"]):
        return "street"

    # 高速赛道
    if length > 6.0 and corners < 15:
        return "high_speed"

    # 技术型赛道
    if corners > 18:
        return "technical"

    # 平衡型
    return "balanced"


def _extract_weather_features(weather: dict[str, Any]) -> dict[str, Any]:
    """提取天气特征（取 FP2 的数据，如果不存在则取第一个可用的）。"""
    if not weather:
        return {
            "air_temp": 25.0,
            "track_temp": 30.0,
            "humidity": 50.0,
            "rainfall": False,
            "wind_speed": 5.0,
        }

    # 优先使用 FP2
    session_key = "FP2" if "FP2" in weather else next(iter(weather.keys()))

    session_weather = weather.get(session_key, {})

    return {
        "air_temp": float(session_weather.get("air_temp", 25.0)),
        "track_temp": float(session_weather.get("track_temp", 30.0)),
        "humidity": float(session_weather.get("humidity", 50.0)),
        "rainfall": bool(session_weather.get("rainfall", False)),
        "wind_speed": float(session_weather.get("wind_speed", 5.0)),
    }


def _extract_qualifying_features(qualifying: list[dict[str, Any]], target_driver: str) -> dict[str, Any]:
    """提取排位赛特征。"""
    if not qualifying:
        return {
            "grid_position": 0,
            "gap_to_pole": 0.0,
            "front_row_density": 0.0,
        }

    # 查找目标车手
    target_pos = None
    for i, driver in enumerate(qualifying):
        driver_name = driver.get("driver", "")
        if _normalize_name(driver_name) == _normalize_name(target_driver):
            target_pos = i + 1
            break

    # 前两排的车队密度（用于评估竞争激烈程度）
    front_row_teams = set()
    for driver in qualifying[:4]:
        team = driver.get("team", "")
        if team:
            front_row_teams.add(team)

    return {
        "grid_position": target_pos if target_pos else 0,
        "gap_to_pole": float(qualifying[0].get("gap_to_pole", 0.0)) if len(qualifying) > 0 else 0.0,
        "front_row_density": len(front_row_teams) / 4.0,  # 多样性指数
    }


def _extract_longrun_features(practice_longruns: dict[str, Any]) -> dict[str, Any]:
    """提取长距离数据特征。"""
    if not practice_longruns:
        return {
            "avg_degradation_soft": 0.0,
            "avg_degradation_medium": 0.0,
            "avg_degradation_hard": 0.0,
            "avg_stint_length": 0,
        }

    degradation_sum = {"SOFT": 0.0, "MEDIUM": 0.0, "HARD": 0.0}
    degradation_count = {"SOFT": 0, "MEDIUM": 0, "HARD": 0}
    stint_lengths = []

    for session_data in practice_longruns.values():
        if not isinstance(session_data, dict):
            continue

        for driver_runs in session_data.values():
            if not isinstance(driver_runs, list):
                continue

            for run in driver_runs:
                compound = run.get("compound", "")
                degradation = run.get("degradation_rate", 0)
                laps = run.get("laps", 0)

                if compound in degradation_sum and degradation > 0:
                    degradation_sum[compound] += degradation
                    degradation_count[compound] += 1

                if laps > 0:
                    stint_lengths.append(laps)

    return {
        "avg_degradation_soft": (
            degradation_sum["SOFT"] / degradation_count["SOFT"]
            if degradation_count["SOFT"] > 0 else 0.0
        ),
        "avg_degradation_medium": (
            degradation_sum["MEDIUM"] / degradation_count["MEDIUM"]
            if degradation_count["MEDIUM"] > 0 else 0.0
        ),
        "avg_degradation_hard": (
            degradation_sum["HARD"] / degradation_count["HARD"]
            if degradation_count["HARD"] > 0 else 0.0
        ),
        "avg_stint_length": sum(stint_lengths) / len(stint_lengths) if stint_lengths else 0,
    }


def _normalize_name(name: str) -> str:
    """标准化车手名称（用于匹配）。"""
    if not name:
        return ""
    # 转小写，移除空格和特殊字符
    return re.sub(r"[^a-z]", "", name.lower())


def state_to_vector(state: dict[str, Any]) -> list[float]:
    """将状态特征转换为固定长度的向量（用于神经网络输入）。

    Returns:
        固定长度的浮点数向量（约 50 维）
    """
    track = state.get("track_features", {})
    weather = state.get("weather_features", {})
    qualifying = state.get("qualifying_features", {})
    longrun = state.get("longrun_features", {})

    # 1. 轨道特征（6维）
    track_type_one_hot = {
        "street": [1, 0, 0],
        "high_speed": [0, 1, 0],
        "technical": [0, 0, 1],
        "balanced": [0.5, 0.5, 0.5],
    }

    vector = [
        # 轨道特征
        track.get("track_length_km", 0) / 10.0,  # 归一化
        track.get("corners", 0) / 20.0,
        track.get("drs_zones", 0) / 4.0,
        track.get("overtaking_difficulty", 0.6),
        *track_type_one_hot.get(track.get("track_type", "balanced"), [0.33, 0.33, 0.33]),

        # 天气特征（5维）
        (weather.get("air_temp", 25.0) - 15.0) / 30.0,  # 归一化到 [0, 1]
        (weather.get("track_temp", 30.0) - 15.0) / 40.0,
        weather.get("humidity", 50.0) / 100.0,
        1.0 if weather.get("rainfall", False) else 0.0,
        weather.get("wind_speed", 5.0) / 20.0,

        # 排位赛特征（3维）
        (qualifying.get("grid_position", 0) - 1) / 19.0 if qualifying.get("grid_position") else 0.5,
        qualifying.get("gap_to_pole", 0.0) / 2.0,
        qualifying.get("front_row_density", 0.5),

        # 长距离特征（4维）
        min(longrun.get("avg_degradation_soft", 0.0) / 0.5, 1.0),
        min(longrun.get("avg_degradation_medium", 0.0) / 0.3, 1.0),
        min(longrun.get("avg_degradation_hard", 0.0) / 0.2, 1.0),
        min(longrun.get("avg_stint_length", 0) / 30.0, 1.0),
    ]

    return vector


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from memory.trace_store import load_trace

    # 列出所有轨迹
    traces = list(Path("../data/traces").glob("*.jsonl"))

    if traces:
        sample_trace_file = traces[0]
        with open(sample_trace_file) as f:
            import json
            sample_trace = json.loads(f.read())

        print("样本轨迹 ID:", sample_trace.get("trace_id"))
        state = extract_state(sample_trace)
        print("\n状态特征:")
        for key, value in state.items():
            print(f"  {key}: {value}")

        vector = state_to_vector(state)
        print(f"\n向量维度: {len(vector)}")
        print(f"向量前10维: {vector[:10]}")
    else:
        print("未找到轨迹文件")