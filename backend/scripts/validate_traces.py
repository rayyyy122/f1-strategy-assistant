"""数据质量验证脚本 — 检查轨迹完整性和奖励分布。"""

import json
from pathlib import Path
from typing import Any

# 导入路径处理
import sys
from pathlib import Path

# 添加 backend 到 path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from backend.memory.trace_store import list_traces, load_trace
from backend.harness.orchestrator import _compute_reward


def validate_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """验证单条轨迹的完整性。

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "warnings": list[str],
        }
    """
    errors = []
    warnings = []

    # 检查必需字段
    required_fields = [
        "trace_id", "timestamp", "mode", "season", "round", "prompt",
        "state", "agent_outputs", "final_prediction",
    ]

    for field in required_fields:
        if field not in trace:
            errors.append(f"缺少必需字段: {field}")
        elif trace[field] is None:
            errors.append(f"字段为空: {field}")

    # 检查 state 结构
    state = trace.get("state", {})
    race_data = state.get("race_data", {})

    if not race_data.get("circuit"):
        errors.append("state.race_data.circuit 缺失")
    if not race_data.get("weather"):
        errors.append("state.race_data.weather 缺失")

    # 检查 agent_outputs
    agent_outputs = trace.get("agent_outputs", {})
    required_agents = ["race_context", "tire_strategist", "competitor_analyst", "synthesis"]

    for agent in required_agents:
        if agent not in agent_outputs:
            errors.append(f"缺少 Agent 输出: {agent}")

    # 检查 final_prediction
    final_prediction = trace.get("final_prediction", {})
    if not final_prediction.get("recommended_strategy"):
        warnings.append("final_prediction 缺少 recommended_strategy")
    if not final_prediction.get("pit_window"):
        warnings.append("final_prediction 缺少 pit_window")
    if not final_prediction.get("predicted_position"):
        warnings.append("final_prediction 缺少 predicted_position")

    # 检查回填状态
    if trace.get("actual_outcome") is None:
        warnings.append("尚未回填 actual_outcome")
    if trace.get("reward") is None:
        warnings.append("尚未回填 reward")

    # 如果已回填，验证奖励计算
    if trace.get("actual_outcome") and trace.get("reward") is not None:
        computed_reward = _compute_reward(final_prediction, trace["actual_outcome"])
        if abs(computed_reward - trace["reward"]) > 0.01:
            errors.append(f"奖励计算不一致: 记录={trace['reward']}, 重新计算={computed_reward}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_all_traces(season: int | None = None) -> dict[str, Any]:
    """验证所有轨迹。"""
    traces = list_traces(season)

    if not traces:
        return {"total": 0, "valid": 0, "invalid": 0, "details": []}

    results = {
        "total": len(traces),
        "valid": 0,
        "invalid": 0,
        "backfilled": 0,
        "reward_stats": [],
        "details": [],
    }

    print(f"验证 {len(traces)} 条轨迹...")

    for trace_info in traces:
        trace = load_trace(trace_info["trace_id"])
        if not trace:
            results["invalid"] += 1
            continue

        validation = validate_trace(trace)

        if validation["valid"]:
            results["valid"] += 1
        else:
            results["invalid"] += 1

        if trace.get("reward") is not None:
            results["backfilled"] += 1
            results["reward_stats"].append(trace["reward"])

        results["details"].append({
            "trace_id": trace_info["trace_id"],
            "season": trace.get("season"),
            "round": trace.get("round"),
            "valid": validation["valid"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "reward": trace.get("reward"),
        })

    # 计算奖励统计
    if results["reward_stats"]:
        results["reward_summary"] = {
            "min": min(results["reward_stats"]),
            "max": max(results["reward_stats"]),
            "avg": sum(results["reward_stats"]) / len(results["reward_stats"]),
            "count": len(results["reward_stats"]),
        }

    return results


def print_validation_report(results: dict[str, Any], verbose: bool = False):
    """打印验证报告。"""
    print("\n" + "=" * 60)
    print("数据质量验证报告")
    print("=" * 60)
    print(f"总轨迹数: {results['total']}")
    print(f"有效轨迹: {results['valid']} ({results['valid']/results['total']*100:.1f}%)")
    print(f"无效轨迹: {results['invalid']} ({results['invalid']/results['total']*100:.1f}%)")
    print(f"已回填: {results['backfilled']} ({results['backfilled']/results['total']*100:.1f}%)")

    if "reward_summary" in results:
        rs = results["reward_summary"]
        print(f"\n奖励统计:")
        print(f"  最小值: {rs['min']:.2f}")
        print(f"  最大值: {rs['max']:.2f}")
        print(f"  平均值: {rs['avg']:.2f}")

    if verbose and results["invalid"] > 0:
        print(f"\n无效轨迹详情:")
        for detail in results["details"]:
            if not detail["valid"]:
                print(f"\n  轨迹 ID: {detail['trace_id']} ({detail['season']} R{detail['round']})")
                if detail["errors"]:
                    print("    错误:")
                    for e in detail["errors"]:
                        print(f"      - {e}")
                if detail["warnings"]:
                    print("    警告:")
                    for w in detail["warnings"]:
                        print(f"      - {w}")


def check_data_quality(results: dict[str, Any]) -> dict[str, Any]:
    """检查数据质量指标。"""
    issues = []
    recommendations = []

    # 检查回填率
    backfill_rate = results["backfilled"] / results["total"] if results["total"] > 0 else 0
    if backfill_rate < 0.5:
        issues.append(f"回填率过低: {backfill_rate*100:.1f}%")
        recommendations.append("运行 `python backfill_traces.py` 回填更多轨迹")

    # 检查奖励分布
    if "reward_summary" in results:
        rs = results["reward_summary"]
        if rs["avg"] < 0:
            issues.append(f"平均奖励过低: {rs['avg']:.2f}")
            recommendations.append("检查奖励计算逻辑或收集更多高质量轨迹")
        if rs["max"] < 0.5:
            issues.append(f"最高奖励过低: {rs['max']:.2f}")
            recommendations.append("当前模型可能需要优化")

    return {
        "issues": issues,
        "recommendations": recommendations,
        "overall_quality": "good" if len(issues) == 0 else "needs_improvement",
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="验证轨迹数据质量")
    parser.add_argument("--season", type=int, help="指定赛季")
    parser.add_argument("--verbose", action="store_true", help="打印详细信息")
    parser.add_argument("--check", action="store_true", help="仅检查回填状态")

    args = parser.parse_args()

    if args.check:
        traces = list_traces(args.season)
        backfilled = sum(1 for t in traces if t.get("reward") is not None)
        print(f"总轨迹: {len(traces)}, 已回填: {backfilled}")
        sys.exit(0 if backfilled == len(traces) else 1)

    results = validate_all_traces(args.season)
    print_validation_report(results, args.verbose)

    quality = check_data_quality(results)
    if quality["issues"]:
        print("\n" + "=" * 60)
        print("数据质量检查")
        print("=" * 60)
        print("发现的问题:")
        for issue in quality["issues"]:
            print(f"  - {issue}")
        print("\n建议:")
        for rec in quality["recommendations"]:
            print(f"  - {rec}")

    print(f"\n总体质量评估: {quality['overall_quality']}")