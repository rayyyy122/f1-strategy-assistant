"""数据集构建器 — 把轨迹转换为 RL 训练样本。

输入: data/traces/*.jsonl（每条轨迹需已回填 reward）
输出: data/rl_dataset.jsonl，每行一个样本:

{
    "trace_id": str,
    "season": int,
    "round": int,
    "state_vector": list[float],   # state_extractor.state_to_vector, ~20 维
    "action_vector": list[float],  # StrategyAction.to_vector, 11 维
    "reward": float,               # 赛后回填的奖励
    "action": dict,                # 可读的策略参数（便于人工检查）
}

用法:
    PYTHONPATH=$PWD python -m backend.rl.dataset_builder
"""

import json
import sys
from collections import Counter
from pathlib import Path

from .state_extractor import extract_state, state_to_vector
from .action_extractor import extract_action

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRACE_DIR = BASE_DIR / "data" / "traces"
OUTPUT_PATH = BASE_DIR / "data" / "rl_dataset.jsonl"


def build_dataset(trace_dir: Path = TRACE_DIR) -> list[dict]:
    """遍历所有轨迹，提取 (state, action, reward) 样本。"""
    samples = []
    skipped = []

    for trace_file in sorted(trace_dir.glob("*.jsonl")):
        try:
            trace = json.loads(trace_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            skipped.append((trace_file.name, f"读取失败: {e}"))
            continue

        if trace.get("reward") is None:
            skipped.append((trace_file.name, "缺少 reward（未回填）"))
            continue

        try:
            state = extract_state(trace)
            action = extract_action(trace.get("agent_outputs", {}))

            samples.append({
                "trace_id": trace.get("trace_id"),
                "season": trace.get("season"),
                "round": trace.get("round"),
                "state_vector": state_to_vector(state),
                "action_vector": action.to_vector(),
                "reward": float(trace["reward"]),
                "action": {
                    "starting_compound": action.starting_compound,
                    "pit_window_start": action.pit_window_start,
                    "pit_window_end": action.pit_window_end,
                    "strategy_type": action.strategy_type,
                },
            })
        except Exception as e:
            skipped.append((trace_file.name, f"提取失败: {e}"))

    return samples, skipped


def print_summary(samples: list[dict]) -> None:
    """打印数据集统计摘要。"""
    rewards = [s["reward"] for s in samples]
    races = Counter(f"{s['season']}_R{s['round']}" for s in samples)
    compounds = Counter(s["action"]["starting_compound"] for s in samples)
    strategies = Counter(s["action"]["strategy_type"] for s in samples)

    print(f"\n样本数: {len(samples)}")
    print(f"状态向量维度: {len(samples[0]['state_vector'])}, 动作向量维度: {len(samples[0]['action_vector'])}")
    print(f"奖励: min={min(rewards):.2f}, max={max(rewards):.2f}, 均值={sum(rewards)/len(rewards):.2f}")
    print(f"\n按比赛分布: {dict(races)}")
    print(f"起跑轮胎分布: {dict(compounds)}")
    print(f"策略类型分布: {dict(strategies)}")


def main() -> None:
    print(f"读取轨迹: {TRACE_DIR}")
    samples, skipped = build_dataset()

    for name, reason in skipped:
        print(f"  跳过 {name}: {reason}")

    if not samples:
        print("没有可用样本，退出")
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print_summary(samples)
    print(f"\n数据集已写入: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
