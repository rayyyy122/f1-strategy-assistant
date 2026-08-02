"""动作提取器 — 从 Agent 输出中解析策略参数。"""

import re
from typing import Any
from dataclasses import dataclass


@dataclass
class StrategyAction:
    """可学习的策略参数。"""
    starting_compound: str  # "SOFT" | "MEDIUM" | "HARD"
    pit_window_start: int
    pit_window_end: int
    strategy_type: str  # "一停" | "二停" | "三停"

    # 辅助参数
    safety_car_sensitivity: float = 0.5  # 安全车敏感度 (0-1)
    undercut_aggressiveness: float = 0.5  # undercut 激进度 (0-1)
    position_over_tire: float = 0.5  # 位置优先 vs 轮胎优先 (0-1)

    def to_vector(self) -> list[float]:
        """转换为向量（用于神经网络）。"""
        # 轮胎配方 one-hot
        compound_one_hot = {
            "SOFT": [1, 0, 0],
            "MEDIUM": [0, 1, 0],
            "HARD": [0, 0, 1],
        }

        # 策略类型 one-hot
        strategy_one_hot = {
            "一停": [1, 0, 0],
            "二停": [0, 1, 0],
            "三停": [0, 0, 1],
        }

        return [
            *compound_one_hot.get(self.starting_compound, [0, 0, 0]),
            self.pit_window_start / 70.0,  # 归一化
            self.pit_window_end / 70.0,
            *strategy_one_hot.get(self.strategy_type, [0, 0, 0]),
            self.safety_car_sensitivity,
            self.undercut_aggressiveness,
            self.position_over_tire,
        ]


def extract_action(agent_outputs: dict[str, Any]) -> StrategyAction:
    """从 Agent 输出中提取策略动作。

    Args:
        agent_outputs: 包含各 Agent 输出的字典

    Returns:
        StrategyAction 对象
    """
    tire_output = agent_outputs.get("tire_strategist", {})
    synthesis_output = agent_outputs.get("synthesis", {})

    # 从 tire_strategist 提取主要参数
    starting_compound = tire_output.get("recommended_compound", "MEDIUM")
    pit_window_start = tire_output.get("pit_window_start", 15)
    pit_window_end = tire_output.get("pit_window_end", 25)
    strategy_type = tire_output.get("strategy_type", "一停")

    # 如果 synthesis 有更详细的信息，优先使用
    if synthesis_output:
        # 尝试从 synthesis 中解析；新格式 pit_window 为按停站拆分的 dict，取第一停
        pit_window_value = synthesis_output.get("pit_window", "")
        if isinstance(pit_window_value, dict):
            pit_window_value = next(iter(pit_window_value.values()), "")
        if pit_window_value:
            parsed = _parse_pit_window(pit_window_value)
            if parsed:
                pit_window_start, pit_window_end = parsed

        # 尝试从 recommended_strategy 文本中解析策略类型
        strategy_text = synthesis_output.get("recommended_strategy", "")
        if strategy_text:
            parsed_type = _parse_strategy_type(strategy_text)
            if parsed_type:
                strategy_type = parsed_type

    # 归一化轮胎配方
    starting_compound = _normalize_compound(starting_compound)

    # 归一化进站窗口
    pit_window_start = max(5, min(pit_window_start, 70))
    pit_window_end = max(pit_window_start, min(pit_window_end, 70))

    # 归一化策略类型
    strategy_type = _normalize_strategy_type(strategy_type)

    return StrategyAction(
        starting_compound=starting_compound,
        pit_window_start=pit_window_start,
        pit_window_end=pit_window_end,
        strategy_type=strategy_type,
    )


def _normalize_compound(compound: str) -> str:
    """归一化轮胎配方。"""
    if not compound:
        return "MEDIUM"

    compound = compound.upper().strip()
    mapping = {
        "S": "SOFT",
        "SOFT": "SOFT",
        "软胎": "SOFT",
        "M": "MEDIUM",
        "MEDIUM": "MEDIUM",
        "中性": "MEDIUM",
        "中胎": "MEDIUM",
        "H": "HARD",
        "HARD": "HARD",
        "硬胎": "HARD",
    }
    return mapping.get(compound, "MEDIUM")


def _normalize_strategy_type(strategy_type: str) -> str:
    """归一化策略类型。"""
    if not strategy_type:
        return "一停"

    strategy_type = strategy_type.strip()
    if any(x in strategy_type for x in ["一停", "1 stop", "1stop"]):
        return "一停"
    if any(x in strategy_type for x in ["二停", "2 stop", "2stop"]):
        return "二停"
    if any(x in strategy_type for x in ["三停", "3 stop", "3stop"]):
        return "三停"
    return "一停"


def _parse_pit_window(text: str) -> tuple[int, int] | None:
    """从文本中提取进站窗口。"""
    if not text or not isinstance(text, str):
        return None

    # 尝试匹配范围 "第20-26圈"
    match = re.search(r"(\d+)\s*[-–—到至]\s*(\d+)", text)
    if match:
        return (int(match.group(1)), int(match.group(2)))

    # 尝试匹配单圈 "第15圈"
    match = re.search(r"(\d+)\s*圈", text)
    if match:
        lap = int(match.group(1))
        return (lap, lap)

    return None


def _parse_strategy_type(text: str) -> str | None:
    """从文本中解析策略类型。"""
    if not text or not isinstance(text, str):
        return None

    if "一停" in text or "1 stop" in text or "1stop" in text:
        return "一停"
    if "二停" in text or "2 stop" in text or "2stop" in text:
        return "二停"
    if "三停" in text or "3 stop" in text or "3stop" in text:
        return "三停"
    return None


def extract_risk_factors(synthesis_output: dict[str, Any]) -> dict[str, float]:
    """提取风险因素（用于辅助参数）。"""
    risk_factors = synthesis_output.get("risk_factors", [])

    safety_car_sensitivity = 0.5
    undercut_aggressiveness = 0.5
    position_over_tire = 0.5

    for risk in risk_factors:
        if isinstance(risk, dict):
            risk_desc = risk.get("risk", "").lower()
            if "安全车" in risk_desc or "safety car" in risk_desc:
                # 安全车风险越高，敏感度越高
                prob_str = risk.get("probability", "50%")
                prob = _parse_probability(prob_str)
                safety_car_sensitivity = max(0.0, min(1.0, prob / 100.0))

            if "undercut" in risk_desc or "undercut" in risk_desc.lower():
                prob_str = risk.get("probability", "50%")
                prob = _parse_probability(prob_str)
                undercut_aggressiveness = max(0.0, min(1.0, prob / 100.0))

    return {
        "safety_car_sensitivity": safety_car_sensitivity,
        "undercut_aggressiveness": undercut_aggressiveness,
        "position_over_tire": position_over_tire,
    }


def _parse_probability(prob_str: str) -> float:
    """从字符串中解析概率。"""
    if not prob_str or not isinstance(prob_str, str):
        return 50.0

    # 提取数字
    match = re.search(r"(\d+)", prob_str)
    if match:
        return float(match.group(1))
    return 50.0


if __name__ == "__main__":
    # 测试代码
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from memory.trace_store import load_trace

    # 测试样本
    sample_agent_outputs = {
        "tire_strategist": {
            "recommended_compound": "MEDIUM",
            "pit_window_start": 18,
            "pit_window_end": 24,
            "strategy_type": "一停",
            "confidence": 0.8,
        },
        "synthesis": {
            "recommended_strategy": "一停策略，第18-24圈进站",
            "pit_window": "第18-24圈",
            "risk_factors": [
                {"risk": "安全车风险", "probability": "25%"},
                {"risk": "Undercut 威胁", "probability": "40%"},
            ],
        }
    }

    action = extract_action(sample_agent_outputs)
    print("提取的动作:")
    print(f"  起跑轮胎: {action.starting_compound}")
    print(f"  进站窗口: {action.pit_window_start}-{action.pit_window_end}圈")
    print(f"  策略类型: {action.strategy_type}")

    vector = action.to_vector()
    print(f"\n动作向量维度: {len(vector)}")
    print(f"动作向量: {vector}")

    risk = extract_risk_factors(sample_agent_outputs["synthesis"])
    print(f"\n风险因素:")
    for k, v in risk.items():
        print(f"  {k}: {v}")