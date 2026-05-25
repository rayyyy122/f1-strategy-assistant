"""轮胎退化计算工具。"""

from .registry import registry


async def _calc_degradation_curve(
    compound: str,
    avg_lap_time: float,
    track_temp_c: float,
    circuit_severity: str = "medium",
) -> dict:
    """根据练习赛数据计算轮胎退化率。

    退化受赛道温度、赛道磨损度、轮胎配方影响。

    Args:
        compound: 轮胎配方 "SOFT" | "MEDIUM" | "HARD"
        avg_lap_time: 该配方的平均圈速（秒）
        track_temp_c: 赛道温度（°C）
        circuit_severity: 赛道磨损度 "low" | "medium" | "high"

    Returns:
        {
            "compound": "MEDIUM",
            "base_degradation": 0.08,       # s/lap 基础退化
            "adjusted_degradation": 0.095,   # 调整后退化
            "estimated_useful_laps": 22,     # 预估可用圈数
            "factors": [...]                 # 调整因子说明
        }
    """
    # 基础退化率（s/lap）：软胎最快退化，硬胎最慢
    base_deg = {"SOFT": 0.15, "MEDIUM": 0.08, "HARD": 0.04}.get(compound, 0.08)

    # 温度因子：赛道温度越高，退化越快
    temp_factor = 1.0
    if track_temp_c > 50:
        temp_factor = 1.3
    elif track_temp_c > 40:
        temp_factor = 1.15
    elif track_temp_c < 25:
        temp_factor = 0.85

    # 赛道磨损因子
    severity_factor = {"low": 0.8, "medium": 1.0, "high": 1.25}.get(circuit_severity, 1.0)

    adjusted = round(base_deg * temp_factor * severity_factor, 3)

    # 预估可用圈数：假设退化超过 1.5s/lap 时轮胎不可用
    useful_laps = max(5, int(1.5 / adjusted)) if adjusted > 0 else 40

    return {
        "compound": compound,
        "base_degradation": base_deg,
        "adjusted_degradation": adjusted,
        "temperature_factor": temp_factor,
        "severity_factor": severity_factor,
        "estimated_useful_laps": useful_laps,
        "factors": [
            f"赛道温度 {track_temp_c}°C，温度因子 {temp_factor}",
            f"赛道磨损度 {circuit_severity}，磨损因子 {severity_factor}",
        ],
    }


async def _estimate_stint_length(
    compound: str,
    degradation_rate: float,
    max_loss_per_lap: float = 1.5,
) -> int:
    """预估某配方轮胎的单段最大圈数。

    Args:
        compound: 轮胎配方
        degradation_rate: 退化率 (s/lap)
        max_loss_per_lap: 允许的最大每圈损失 (s)

    Returns:
        预估可用圈数
    """
    return max(5, int(max_loss_per_lap / degradation_rate)) if degradation_rate > 0 else 50


registry.register(
    name="calc_degradation_curve",
    description="计算指定配方轮胎的退化曲线：基础退化率、温度和赛道磨损调整后的退化率、预估可用圈数。需要练习赛平均圈速、赛道温度和赛道磨损度作为输入。",
    func=_calc_degradation_curve,
    parameters_schema={
        "type": "object",
        "properties": {
            "compound": {
                "type": "string",
                "enum": ["SOFT", "MEDIUM", "HARD"],
                "description": "轮胎配方",
            },
            "avg_lap_time": {
                "type": "number",
                "description": "该配方的平均圈速（秒）",
            },
            "track_temp_c": {
                "type": "number",
                "description": "赛道温度（°C）",
            },
            "circuit_severity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "赛道磨损度",
            },
        },
        "required": ["compound", "avg_lap_time", "track_temp_c"],
    },
    agents=["tire_strategist"],
)

registry.register(
    name="estimate_stint_length",
    description="根据退化率预估某配方轮胎可用圈数。",
    func=_estimate_stint_length,
    parameters_schema={
        "type": "object",
        "properties": {
            "compound": {
                "type": "string",
                "enum": ["SOFT", "MEDIUM", "HARD"],
            },
            "degradation_rate": {
                "type": "number",
                "description": "退化率 (s/lap)",
            },
        },
        "required": ["compound", "degradation_rate"],
    },
    agents=["tire_strategist"],
)