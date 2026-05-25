"""策略合理性校验。"""

from ..models.schemas import TireStrategyOutput, SynthesisOutput


def validate_tire_strategy(output: TireStrategyOutput) -> list[str]:
    """校验轮胎策略输出是否合理。返回警告列表，空列表表示通过。"""
    warnings = []

    # 进站窗在合理范围
    if output.pit_window_start < 1:
        warnings.append("进站窗口开始圈数无效")
    if output.pit_window_end > 80:
        warnings.append("进站窗口结束圈数超出正常范围")
    if output.pit_window_start >= output.pit_window_end:
        warnings.append("进站窗口开始 >= 结束")

    # 轮胎配方合理
    if output.recommended_compound not in ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"):
        warnings.append(f"未知轮胎配方: {output.recommended_compound}")

    # 退化率合理
    if output.degradation_rate_medium is not None:
        if output.degradation_rate_medium < 0:
            warnings.append("退化率不能为负")
        if output.degradation_rate_medium > 0.5:
            warnings.append(f"退化率异常高: {output.degradation_rate_medium}s/lap")

    # 置信度
    if output.confidence < 0 or output.confidence > 1:
        warnings.append("置信度超出 [0,1] 范围")

    return warnings


def validate_synthesis(output: SynthesisOutput) -> list[str]:
    """校验综合策略输出。"""
    warnings = []

    if not output.recommended_strategy:
        warnings.append("缺少推荐策略")
    if output.confidence < 0 or output.confidence > 1:
        warnings.append("置信度超出 [0,1] 范围")
    if output.confidence < 0.5:
        warnings.append(f"置信度过低 ({output.confidence})，建议获取更多数据")

    return warnings