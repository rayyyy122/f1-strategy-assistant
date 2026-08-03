"""轨迹回填脚本 — 从 FastF1 加载实际比赛结果并回填奖励。"""

import asyncio
from pathlib import Path
from typing import Any
import sys

# 添加 backend 到 path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from backend.memory.trace_store import list_traces, load_trace, backfill_outcome
from backend.tools.strategy_tools import _load_actual_race_result
from backend.harness.orchestrator import _compute_reward


async def backfill_single_trace(trace_id: str, dry_run: bool = False, force: bool = False) -> tuple[bool, str]:
    """回填单条轨迹。

    force=True 时用已存的 actual_outcome 重新计算 reward（不重新加载 FastF1），
    用于 reward 规则变更后的全量重算。

    Returns:
        (success, message)
    """
    trace = load_trace(trace_id)
    if not trace:
        return (False, f"轨迹 {trace_id} 不存在")

    actual = trace.get("actual_outcome")
    if actual is not None and not force:
        return (True, "已回填")

    season = trace.get("season")
    round_num = trace.get("round")

    if not season or not round_num:
        return (False, "缺少 season 或 round")

    if actual is None or "error" in actual or not actual.get("results"):
        # 首次回填：从 FastF1 加载实际结果
        actual = await _load_actual_race_result(season, round_num)

        if "error" in actual or not actual.get("results"):
            return (False, f"未找到 {season} R{round_num} 的比赛结果: {actual.get('error', '未知错误')}")

    # 计算奖励（对比对象为轨迹的目标车手）
    driver = (trace.get("state") or {}).get("driver", "")
    final_prediction = trace.get("final_prediction", {})
    reward = _compute_reward(final_prediction, actual, target_driver=driver)

    message = f"赛季 {season} R{round_num}: reward={reward}, 来源={actual.get('source')}"

    if dry_run:
        return (True, f"[DRY RUN] {message}")

    # 回填
    backfill_outcome(trace_id, actual, reward)
    return (True, message)


async def backfill_all_traces(
    season: int | None = None,
    dry_run: bool = False,
    verbose: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """批量回填所有轨迹。

    Args:
        season: 指定赛季，None 表示所有赛季
        dry_run: 是否只模拟不实际写入
        verbose: 是否打印详细信息
        force: 是否强制重算 reward（复用已存 actual_outcome）

    Returns:
        统计信息
    """
    traces = list_traces(season)

    if not traces:
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    results = {
        "total": len(traces),
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    print(f"找到 {len(traces)} 条轨迹需要回填...")

    for trace_info in traces:
        trace_id = trace_info["trace_id"]

        if verbose:
            print(f"处理轨迹: {trace_id}...", end=" ")

        try:
            success, message = await asyncio.wait_for(
                backfill_single_trace(trace_id, dry_run, force=force), timeout=600
            )
        except asyncio.TimeoutError:
            success, message = False, "回填超时（600s），稍后可重跑续传"

        if success:
            if "已回填" in message:
                results["skipped"] += 1
                if verbose:
                    print(f"跳过 ({message})")
            else:
                results["success"] += 1
                if verbose:
                    print(f"✓ ({message})")
        else:
            results["failed"] += 1
            if verbose:
                print(f"✗ ({message})")

        results["details"].append({
            "trace_id": trace_id,
            "success": success,
            "message": message,
        })

    return results


def print_summary(results: dict[str, Any]):
    """打印回填结果摘要。"""
    print("\n" + "=" * 50)
    print("回填结果摘要")
    print("=" * 50)
    print(f"总轨迹数: {results['total']}")
    print(f"成功回填: {results['success']}")
    print(f"已回填跳过: {results['skipped']}")
    print(f"失败: {results['failed']}")

    if results["success"] > 0:
        print(f"\n成功率: {results['success'] / results['total'] * 100:.1f}%")

    if results["failed"] > 0:
        print("\n失败的轨迹:")
        for detail in results["details"]:
            if not detail["success"]:
                print(f"  - {detail['trace_id']}: {detail['message']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="回填 F1 比赛轨迹的实际结果")
    parser.add_argument("--season", type=int, help="指定赛季")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际写入")
    parser.add_argument("--trace-id", type=str, help="指定单条轨迹 ID")
    parser.add_argument("--verbose", action="store_true", default=True, help="打印详细信息")
    parser.add_argument("--force", action="store_true", help="强制重算 reward（复用已存结果，用于规则变更后）")

    args = parser.parse_args()

    async def main():
        if args.trace_id:
            success, message = await backfill_single_trace(args.trace_id, args.dry_run, force=args.force)
            print(f"{'[DRY RUN] ' if args.dry_run else ''}{message}")
        else:
            results = await backfill_all_traces(
                season=args.season,
                dry_run=args.dry_run,
                verbose=args.verbose,
                force=args.force,
            )
            print_summary(results)

    asyncio.run(main())