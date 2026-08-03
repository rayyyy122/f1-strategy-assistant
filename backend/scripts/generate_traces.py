"""批量轨迹生成脚本 — 对历史比赛批量跑赛前分析，生成 RL 训练轨迹。

流程：
1. 从 Jolpica 拉赛季日程 + 排位结果，每场选 N 个代表性车手（杆位/中游/队尾）
2. 对每个 (比赛, 车手) 调 handle_prompt 跑完整 4-Agent 赛前分析（轨迹自动保存）
3. 全部生成完后自动回填 reward（历史比赛真实结果已知）
4. 打印审计表（预测名次 vs 实际名次 vs reward），供人工抽查

用法:
    PYTHONPATH=$PWD python -m backend.scripts.generate_traces --season 2024 --rounds 1-7,9-18
    PYTHONPATH=$PWD python -m backend.scripts.generate_traces --season 2024 --rounds 3 --drivers-per-race 1 --dry-run
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

# 保证可以独立运行（不依赖 PYTHONPATH）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.data.jolpica_client import get_season_schedule, get_qualifying_results
from backend.harness.orchestrator import handle_prompt, _compute_reward
from backend.memory.trace_store import TRACE_DIR, load_trace, backfill_outcome
from backend.tools.strategy_tools import _load_actual_race_result


# ---- 工具函数 ----

def normalize_name(name: str) -> str:
    """车手名标准化（用于匹配）。"""
    return re.sub(r"[^a-z]", "", (name or "").lower())


def parse_rounds(spec: str, max_round: int) -> set[int]:
    """解析轮次规格: 'all' / '1-7,9-18' / '3,5,8'。"""
    if spec == "all":
        return set(range(1, max_round + 1))
    rounds = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            rounds.update(range(int(a), int(b) + 1))
        elif part:
            rounds.add(int(part))
    return {r for r in rounds if 1 <= r <= max_round}


def existing_trace_keys() -> set[tuple[int, int, str]]:
    """已有轨迹的 (season, round, driver) 集合，用于去重。"""
    keys = set()
    for filepath in TRACE_DIR.glob("*.jsonl"):
        try:
            trace = json.loads(filepath.read_text().strip().split("\n")[-1])
            driver = (trace.get("state") or {}).get("driver", "")
            keys.add((trace.get("season"), trace.get("round"), normalize_name(driver)))
        except Exception:
            continue
    return keys


def pick_drivers(qualifying: list[dict], n: int) -> list[dict]:
    """从排位结果选 n 个代表性车手：杆位(P1) / 中游(P10) / 队尾(P17)。"""
    grid = []
    for q in qualifying:
        drv = q.get("Driver", {})
        name = f"{drv.get('givenName', '')} {drv.get('familyName', '')}".strip()
        team = q.get("Constructor", {}).get("name", "")
        if name:
            grid.append({"name": name, "team": team})

    picks = []
    for idx in [0, 9, 16][:max(1, min(n, 3))]:
        if idx < len(grid):
            picks.append(grid[idx])
    return picks


# ---- 单次分析 ----

async def run_one(prompt: str, timeout_s: int = 600) -> tuple[str, str, dict]:
    """跑一次完整分析，消费全部 SSE 事件。

    Returns:
        (status, message, usage)  status ∈ ok / clarification / error / timeout / exception
    """
    status, message, usage = "ok", "", {}

    async def consume():
        nonlocal status, message, usage
        async for event in handle_prompt(prompt):
            etype = event.get("type")
            if etype == "clarification_needed":
                status, message = "clarification", event.get("message", "")
            elif etype == "error":
                status, message = "error", event.get("message", "")
            elif etype == "complete":
                usage = event.get("usage", {})

    try:
        await asyncio.wait_for(consume(), timeout=timeout_s)
    except asyncio.TimeoutError:
        status, message = "timeout", f"超过 {timeout_s}s"
    except Exception as e:
        status, message = "exception", str(e)

    return status, message, usage


async def backfill_new(trace_id: str) -> tuple[bool, float | None, str]:
    """回填单条新生成的轨迹。"""
    trace = load_trace(trace_id)
    if not trace:
        return False, None, "轨迹不存在"
    actual = await _load_actual_race_result(trace["season"], trace["round"])
    if "error" in actual or not actual.get("results"):
        return False, None, actual.get("error", "无结果")
    reward = _compute_reward(
        trace.get("final_prediction", {}),
        actual,
        target_driver=(trace.get("state") or {}).get("driver", ""),
    )
    backfill_outcome(trace_id, actual, reward)
    return True, reward, ""


def find_actual_position(actual_outcome: dict, driver: str) -> int | None:
    """在实际结果中按车手名找名次。"""
    target = normalize_name(driver)
    for r in actual_outcome.get("results", []):
        if normalize_name(r.get("driver", "")) == target:
            return r.get("position")
        if normalize_name(r.get("driver_code", "")) == target:
            return r.get("position")
    return None


# ---- 主流程 ----

async def main() -> None:
    parser = argparse.ArgumentParser(description="批量生成 RL 训练轨迹")
    parser.add_argument("--season", type=int, required=True, help="赛季年份（需已完赛）")
    parser.add_argument("--rounds", type=str, default="all", help="轮次: all / 1-7,9-18 / 3,5,8")
    parser.add_argument("--drivers-per-race", type=int, default=2, help="每场车手数 (1-3)，默认 2")
    parser.add_argument("--delay", type=float, default=3.0, help="每次分析间隔秒数")
    parser.add_argument("--timeout", type=int, default=600, help="单次分析超时秒数")
    parser.add_argument("--include-existing", action="store_true", help="不跳过已有 (场次,车手) 组合")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不实际调用 LLM")
    args = parser.parse_args()

    print(f"加载 {args.season} 赛季日程...", flush=True)
    schedule = await get_season_schedule(args.season)
    rounds = parse_rounds(args.rounds, max_round=len(schedule))
    races = [r for r in schedule if int(r["round"]) in rounds]
    existing = existing_trace_keys()

    # ---- 构建计划 ----
    plan = []
    for race in races:
        round_num = int(race["round"])
        race_name = race.get("raceName", f"R{round_num}")
        try:
            quali = await get_qualifying_results(args.season, round_num)
        except Exception as e:
            print(f"  跳过 R{round_num} {race_name}（排位数据获取失败: {e}）", flush=True)
            continue
        for d in pick_drivers(quali, args.drivers_per_race):
            key = (args.season, round_num, normalize_name(d["name"]))
            if key in existing and not args.include_existing:
                print(f"  跳过已存在: R{round_num} {d['name']}", flush=True)
                continue
            plan.append({
                "round": round_num,
                "race_name": race_name,
                "driver": d["name"],
                "team": d["team"],
            })

    print(f"\n计划生成 {len(plan)} 条轨迹（{len(races)} 场比赛 × 每场最多 {args.drivers_per_race} 车手）:", flush=True)
    for p in plan:
        print(f"  R{p['round']:<3} {p['race_name']:<35} {p['driver']}", flush=True)

    if args.dry_run:
        print("\n[DRY RUN] 未实际执行")
        return

    if not plan:
        print("没有需要生成的轨迹")
        return

    # ---- 逐条生成 ----
    results = []
    total_usage = {"input_tokens": 0, "output_tokens": 0}

    for i, item in enumerate(plan, 1):
        prompt = (
            f"分析{args.season}赛季第{item['round']}站{item['race_name']}，"
            f"{item['team']}车队{item['driver']}的正赛策略，"
            f"给出起步轮胎配方、进站窗口和停站次数建议"
        )
        print(f"\n[{i}/{len(plan)}] R{item['round']} {item['race_name']} · {item['driver']}", flush=True)

        before = set(TRACE_DIR.glob("*.jsonl"))
        status, message, usage = await run_one(prompt, timeout_s=args.timeout)
        new_files = set(TRACE_DIR.glob("*.jsonl")) - before

        trace_id = new_files.pop().stem if new_files else None
        total_usage["input_tokens"] += usage.get("input_tokens", 0)
        total_usage["output_tokens"] += usage.get("output_tokens", 0)

        results.append({**item, "status": status, "message": message, "trace_id": trace_id})
        print(f"  → {status} trace={trace_id} tokens={usage.get('input_tokens', 0)}+{usage.get('output_tokens', 0)}"
              + (f" ({message[:80]})" if message else ""), flush=True)

        if i < len(plan):
            await asyncio.sleep(args.delay)

    # ---- 回填 ----
    print(f"\n{'=' * 60}\n生成完成，开始回填 reward...\n{'=' * 60}", flush=True)
    for r in results:
        if not r.get("trace_id"):
            continue
        try:
            ok, reward, err = await asyncio.wait_for(backfill_new(r["trace_id"]), timeout=600)
        except asyncio.TimeoutError:
            ok, reward, err = False, None, "回填超时（600s），可用 backfill_traces.py 续传"
        r["reward"] = reward
        print(f"  {r['trace_id']}: {'reward=' + f'{reward:.2f}' if ok else '回填失败: ' + err}", flush=True)

    # ---- 审计表 ----
    print(f"\n{'=' * 60}")
    print("审计表（抽查用：预测名次 vs 实际名次 vs reward 是否合理）")
    print(f"{'=' * 60}")
    print(f"{'场次':<6}{'车手':<22}{'预测':<10}{'实际':<8}{'reward':<8}{'状态'}")
    for r in results:
        predicted, actual_pos, reward_str = "-", "-", "-"
        if r.get("trace_id"):
            trace = load_trace(r["trace_id"]) or {}
            pred = (trace.get("final_prediction") or {}).get("predicted_position", "")
            m = re.search(r"P(\d+)", str(pred))
            predicted = f"P{m.group(1)}" if m else str(pred)[:6]
            pos = find_actual_position(trace.get("actual_outcome") or {}, r["driver"])
            actual_pos = f"P{pos}" if pos is not None else "?"
            if r.get("reward") is not None:
                reward_str = f"{r['reward']:.2f}"
        print(f"R{r['round']:<5}{r['driver']:<22}{predicted:<10}{actual_pos:<8}{reward_str:<8}{r['status']}")

    # ---- 汇总 ----
    ok_count = sum(1 for r in results if r["status"] == "ok" and r.get("trace_id"))
    print(f"\n成功 {ok_count}/{len(plan)}，"
          f"总 tokens: 输入 {total_usage['input_tokens']}, 输出 {total_usage['output_tokens']}")
    print("后续: PYTHONPATH=$PWD python -m backend.rl.dataset_builder && PYTHONPATH=$PWD python -m backend.rl.train")


if __name__ == "__main__":
    asyncio.run(main())
