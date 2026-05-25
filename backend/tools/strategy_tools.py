"""策略对比/模拟工具。"""

import json
from pathlib import Path
from .registry import registry
from ..data import fastf1_client, jolpica_client
from ..config import TRACE_DIR


async def _load_actual_race_result(year: int, round_num: int) -> dict:
    """加载真实比赛结果（正赛排名和策略）。"""
    try:
        session = fastf1_client.load_session(year, round_num, "R")
        laps = session.laps

        results = []
        for driver in laps["Driver"].unique():
            driver_laps = laps[laps["Driver"] == driver]
            last_lap = driver_laps[driver_laps["LapNumber"] == driver_laps["LapNumber"].max()]
            if last_lap.empty:
                continue
            last = last_lap.iloc[0]

            # 计算总时间
            total_seconds = None
            if hasattr(driver_laps["LapTime"], "sum"):
                total_seconds = driver_laps["LapTime"].sum().total_seconds()

            results.append({
                "driver": driver,
                "position": int(last["Position"]) if hasattr(last, "Position") else 0,
                "total_time_seconds": round(total_seconds, 1) if total_seconds else None,
                "laps_completed": int(last["LapNumber"]),
            })

        results.sort(key=lambda x: x["position"])
        return {"year": year, "round": round_num, "results": results}
    except Exception as e:
        return {"error": f"加载比赛结果失败: {e}"}


async def _compare_prediction_vs_actual(trace_id: str) -> dict:
    """对比预测结果和实际比赛结果。"""
    trace_path = TRACE_DIR / f"{trace_id}.jsonl"
    if not trace_path.exists():
        return {"error": f"轨迹 {trace_id} 不存在"}

    # 读取轨迹（取最后一条）
    lines = trace_path.read_text().strip().split("\n")
    if not lines:
        return {"error": "轨迹为空"}

    trace = json.loads(lines[-1])
    prediction = trace.get("final_prediction", {})
    actual = trace.get("actual_outcome", {})

    return {
        "trace_id": trace_id,
        "prediction": prediction,
        "actual": actual,
        "prediction_matches": prediction.get("predicted_position") == actual.get("actual_position"),
    }


TRACE_DIR.mkdir(parents=True, exist_ok=True)


registry.register(
    name="load_actual_race_result",
    description="加载一场已完成的F1比赛的正赛结果：各车手最终排名、总时间、完成圈数。",
    func=_load_actual_race_result,
    parameters_schema={
        "type": "object",
        "properties": {
            "year": {"type": "integer", "description": "赛季年份"},
            "round_num": {"type": "integer", "description": "比赛轮次"},
        },
        "required": ["year", "round_num"],
    },
)

registry.register(
    name="compare_prediction_vs_actual",
    description="对比 Agent 的策略预测和实际比赛结果，分析差异原因。",
    func=_compare_prediction_vs_actual,
    parameters_schema={
        "type": "object",
        "properties": {
            "trace_id": {"type": "string", "description": "预测轨迹 ID"},
        },
        "required": ["trace_id"],
    },
)