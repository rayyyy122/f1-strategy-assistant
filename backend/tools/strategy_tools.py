"""策略对比/模拟工具。"""

import json
import math
import asyncio
from pathlib import Path
from .registry import registry
from ..data import fastf1_client, jolpica_client
from ..config import TRACE_DIR


def _safe_int(value, default=None):
    """转 int，NaN/None/无效值返回 default。"""
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _extract_race_strategies(session) -> dict[str, dict]:
    """从 session.laps 提取每位车手的进站策略。

    通过 Compound 切换自动推算进站。F1 比赛中除红旗外无法不通过进站换胎，
    因此连续圈之间的 Compound 变化 = 一次进站。

    **红旗过滤**：如果同一圈有 >= 一半车手同时换胎，判定为红旗重开，整圈不计入进站。

    Returns:
        {driver_code: {
            "stops": int,           # 进站次数
            "strategy": str,        # "一停" / "二停" / "三停" / "零停"
            "compounds": [str],     # 配方序列（起步配方 → 停1后……）
            "pit_laps": [int],      # 出场圈 lap number
        }, ...}
    """
    strategies: dict[str, dict] = {}

    try:
        laps = session.laps
    except Exception:
        return strategies

    # Step 1：收集每个车手的 compound 切换点
    raw_transitions: dict[str, list[tuple[str, int]]] = {}  # driver → [(compound, first_lap), ...]

    for driver in laps["Driver"].unique():
        driver_laps = laps[laps["Driver"] == driver].sort_values("LapNumber")
        if driver_laps.empty:
            continue

        seq: list[tuple[str, int]] = []
        for _, lap in driver_laps.iterrows():
            compound = str(lap["Compound"])
            lap_num = _safe_int(lap.get("LapNumber"), 0)
            if not seq or seq[-1][0] != compound:
                seq.append((compound, lap_num))
        raw_transitions[str(driver)] = seq

    # Step 2：检测红旗 — 同圈 >= 一半车手都换胎
    total_drivers = len(raw_transitions)
    lap_transition_count: dict[int, int] = {}
    for seq in raw_transitions.values():
        for _, lap_num in seq[1:]:  # 跳过起步配方
            lap_transition_count[lap_num] = lap_transition_count.get(lap_num, 0) + 1

    red_flag_laps: set[int] = set()
    threshold = max(total_drivers // 2, 1)
    for lap_num, count in lap_transition_count.items():
        if lap_num <= 3 and count >= threshold:
            red_flag_laps.add(lap_num)

    # Step 3：过滤红旗后构建最终策略
    for driver, seq in raw_transitions.items():
        filtered: list[tuple[str, int]] = [seq[0]]  # 起步配方保留
        for compound, lap_num in seq[1:]:
            if lap_num not in red_flag_laps:
                filtered.append((compound, lap_num))

        if len(filtered) <= 1:
            # 仅起步配方 → 0 停（红旗换胎不算进站）
            continue

        stops = len(filtered) - 1
        if stops == 1:
            type_str = "一停"
        elif stops == 2:
            type_str = "二停"
        elif stops >= 3:
            type_str = f"{stops}停"
        else:
            type_str = "零停"

        compound_names = [c for c, _ in filtered]
        pit_laps = [n for _, n in filtered[1:]]

        strategies[driver] = {
            "stops": stops,
            "strategy": type_str,
            "compounds": compound_names,
            "pit_laps": pit_laps,
        }

    return strategies


async def _load_actual_race_result(year: int, round_num: int) -> dict:
    """加载真实比赛结果（正赛排名）+ 每车手进站策略。

    优先使用 session.results（FastF1 官方分类排名，包含 DNF/DSQ 处理），
    退回到 laps 数据作为备选。
    进站策略通过 session.laps 的 Compound 切换自动推算。
    """
    try:
        session = await asyncio.to_thread(fastf1_client.load_session, year, round_num, "R")
    except Exception as e:
        return {"error": f"加载比赛 session 失败 ({year} R{round_num}): {e}"}

    # ---- 提取每车手进站策略（两个结果路径共享） ----
    strategies = _extract_race_strategies(session)

    # 优先用 session.results
    try:
        sr = session.results
        if sr is not None and len(sr) > 0:
            results = []
            for _, row in sr.iterrows():
                pos = _safe_int(row.get("Position"))
                classified = str(row.get("ClassifiedPosition", "") or "").strip()
                status = str(row.get("Status", "") or "").strip()

                # DNF/DSQ 等用 classified position 标识
                if pos is None and classified:
                    # classified 可能是 "1", "2", ... 或 "DNF", "DSQ", "NC"
                    pos_from_class = _safe_int(classified)
                    if pos_from_class is None:
                        # 非数字（DNF 等），排在已完赛之后
                        pos = 99
                    else:
                        pos = pos_from_class

                driver_code = str(row.get("Abbreviation", row.get("DriverNumber", "")))
                full_name = str(row.get("FullName", driver_code))
                team = str(row.get("TeamName", ""))

                results.append({
                    "driver": full_name or driver_code,
                    "driver_code": driver_code,
                    "team": team,
                    "position": pos if pos is not None else 99,
                    "status": status,
                    "classified": classified,
                    "points": _safe_float(row.get("Points"), 0),
                    "grid": _safe_int(row.get("GridPosition")),
                })

            results.sort(key=lambda x: x["position"])
            return {"year": year, "round": round_num, "source": "session.results", "results": results, "strategies": strategies}
    except Exception as e:
        # 回退到 laps
        pass

    # 回退方案：基于 laps 数据
    try:
        laps = session.laps
        results = []
        for driver in laps["Driver"].unique():
            driver_laps = laps[laps["Driver"] == driver]
            last_lap = driver_laps.tail(1)
            if last_lap.empty:
                continue
            last = last_lap.iloc[0]

            position = _safe_int(last.get("Position"))
            laps_completed = _safe_int(last.get("LapNumber"), 0)

            results.append({
                "driver": str(driver),
                "position": position if position is not None else 99,
                "laps_completed": laps_completed,
            })

        results.sort(key=lambda x: x["position"])
        return {"year": year, "round": round_num, "source": "laps", "results": results, "strategies": strategies}
    except Exception as e:
        return {"error": f"加载比赛结果失败: {e}"}


async def _compare_prediction_vs_actual(trace_id: str) -> dict:
    """对比预测结果和实际比赛结果。"""
    trace_path = TRACE_DIR / f"{trace_id}.jsonl"
    if not trace_path.exists():
        return {"error": f"轨迹 {trace_id} 不存在"}

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
    description="加载一场已完成的F1比赛的正赛结果：各车手最终排名、车队、状态、积分。",
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