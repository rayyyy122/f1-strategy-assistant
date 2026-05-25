"""RL 轨迹存储 — JSONL 格式。"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from ..config import TRACE_DIR


def save_trace(
    mode: str,
    season: int | None,
    round_num: int | None,
    prompt: str,
    state: dict,
    agent_outputs: dict[str, dict],
    final_prediction: dict,
    trace_id: str | None = None,
) -> str:
    """保存一条完整的规划轨迹。

    Returns:
        trace_id
    """
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    if trace_id is None:
        trace_id = f"{season or 'general'}_R{round_num or 'X'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    record = {
        "trace_id": trace_id,
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "season": season,
        "round": round_num,
        "prompt": prompt,
        "state": state,
        "agent_outputs": agent_outputs,
        "final_prediction": final_prediction,
        "actual_outcome": None,
        "reward": None,
    }

    filepath = TRACE_DIR / f"{trace_id}.jsonl"
    with open(filepath, "w") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return trace_id


def load_trace(trace_id: str) -> dict | None:
    """加载指定轨迹。"""
    filepath = TRACE_DIR / f"{trace_id}.jsonl"
    if not filepath.exists():
        return None
    lines = filepath.read_text().strip().split("\n")
    return json.loads(lines[-1]) if lines else None


def backfill_outcome(trace_id: str, actual_outcome: dict, reward: float):
    """赛后回填实际结果和奖励。"""
    filepath = TRACE_DIR / f"{trace_id}.jsonl"
    if not filepath.exists():
        raise FileNotFoundError(f"轨迹 {trace_id} 不存在")

    with open(filepath, "r") as f:
        record = json.loads(f.readlines()[-1])

    record["actual_outcome"] = actual_outcome
    record["reward"] = reward
    record["backfilled_at"] = datetime.now().isoformat()

    with open(filepath, "w") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def list_traces(season: int | None = None) -> list[dict]:
    """列出所有轨迹（可按赛季过滤）。"""
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    traces = []
    for filepath in sorted(TRACE_DIR.glob("*.jsonl")):
        try:
            lines = filepath.read_text().strip().split("\n")
            trace = json.loads(lines[-1])
            if season is None or trace.get("season") == season:
                traces.append({
                    "trace_id": trace["trace_id"],
                    "mode": trace["mode"],
                    "season": trace.get("season"),
                    "round": trace.get("round"),
                    "timestamp": trace.get("timestamp"),
                    "reward": trace.get("reward"),
                })
        except Exception:
            continue
    return traces


def compute_accuracy(season: int | None = None) -> dict:
    """统计预测准确率。"""
    traces = list_traces(season)
    if not traces:
        return {"total": 0}

    with_actual = [t for t in traces if t["reward"] is not None]
    if not with_actual:
        return {"total": len(traces), "backfilled": 0}

    correct = sum(1 for t in with_actual if t["reward"] is not None and t["reward"] > 0)
    total_reward = sum(t["reward"] for t in with_actual if t["reward"] is not None)

    return {
        "total_traces": len(traces),
        "backfilled": len(with_actual),
        "correct_predictions": correct,
        "accuracy": round(correct / len(with_actual), 3) if with_actual else 0,
        "avg_reward": round(total_reward / len(with_actual), 3) if with_actual else 0,
    }