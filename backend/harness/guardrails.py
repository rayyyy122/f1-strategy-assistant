"""策略合理性校验 — 接受 raw dict（兼容 Agent JSON 输出），返回警告列表。"""

from typing import Any

# 合法比赛轮胎配方
_VALID_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}


def validate_tire_strategy(output: dict[str, Any]) -> list[str]:
    """校验轮胎策略输出。空列表 = 通过。"""
    warnings: list[str] = []

    if not isinstance(output, dict):
        return ["轮胎策略输出不是 JSON 对象"]

    # ---- 进站窗口 ----
    start = output.get("pit_window_start")
    end = output.get("pit_window_end")
    if not isinstance(start, (int, float)) or start < 1:
        warnings.append(f"进站窗口开始圈数无效: {start}")
    if not isinstance(end, (int, float)) or end > 80:
        warnings.append(f"进站窗口结束圈数超出正常范围: {end}")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and start >= end:
        warnings.append(f"进站窗口开始 >= 结束 ({start} >= {end})")

    # ---- 轮胎配方 ----
    compound = output.get("recommended_compound", "")
    if compound and str(compound).upper() not in _VALID_COMPOUNDS:
        warnings.append(f"未知轮胎配方: {compound}")

    # ---- 退化率 ----
    for key, label in [
        ("degradation_rate_soft", "软胎"),
        ("degradation_rate_medium", "中性胎"),
        ("degradation_rate_hard", "硬胎"),
    ]:
        rate = output.get(key)
        if rate is not None and isinstance(rate, (int, float)):
            if rate < 0:
                warnings.append(f"{label}退化率不能为负: {rate}")
            if rate > 0.5:
                warnings.append(f"{label}退化率异常高: {rate}s/lap")

    # ---- 置信度 ----
    conf = output.get("confidence")
    if conf is not None:
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            warnings.append(f"置信度超出 [0,1] 范围: {conf}")
        elif conf < 0.4:
            warnings.append(f"轮胎策略置信度过低 ({conf})，建议获取更多练习赛数据或切换保守策略")

    return warnings


def validate_synthesis(output: dict[str, Any]) -> list[str]:
    """校验综合策略输出。空列表 = 通过。"""
    warnings: list[str] = []

    if not isinstance(output, dict):
        return ["综合策略输出不是 JSON 对象"]

    # ---- 推荐策略 ----
    strategy = output.get("recommended_strategy", "")
    if not strategy or not str(strategy).strip():
        warnings.append("缺少推荐策略")

    # ---- 风险因子 ----
    risk_factors = output.get("risk_factors")
    if not risk_factors or (isinstance(risk_factors, list) and len(risk_factors) == 0):
        warnings.append("策略未列出任何风险因子，可能过于乐观")

    # ---- 备选方案 ----
    alternatives = output.get("alternatives")
    if not alternatives or (isinstance(alternatives, list) and len(alternatives) == 0):
        warnings.append("策略未提供备选方案")

    # ---- 置信度 ----
    conf = output.get("confidence")
    if conf is not None:
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            warnings.append(f"综合置信度超出 [0,1] 范围: {conf}")
        elif conf < 0.5:
            warnings.append(f"综合置信度偏低 ({conf})，建议标注为'低置信度'并告知用户")
        elif conf < 0.3:
            warnings.append(f"综合置信度过低 ({conf})，强烈建议拒绝给出策略并建议用户提供更多数据")

    return warnings