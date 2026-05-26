import type { ComparisonData } from "../types";

export function ComparisonCard({ comparison }: { comparison: ComparisonData }) {
  const { actual, prediction, has_prediction, reward, trace_id } = comparison;

  return (
    <div className="bg-blue-950/20 border border-blue-600/30 rounded-lg p-4 text-sm">
      <div className="text-blue-400 font-bold mb-3 text-base">赛后复盘</div>

      {!has_prediction && (
        <div className="text-zinc-400 text-sm mb-3">
          暂无该比赛的 Agent 预测数据，无法对比。先进行一次赛前策略分析后，再来复盘吧。
        </div>
      )}

      {/* 实际结果表格 */}
      {actual.results && actual.results.length > 0 && (
        <div className="mb-3">
          <div className="text-zinc-500 text-xs mb-1.5">🏁 实际比赛结果</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1">P</th>
                <th className="text-left py-1">车手</th>
                <th className="text-right py-1">总时间</th>
              </tr>
            </thead>
            <tbody>
              {actual.results.slice(0, 5).map((r) => (
                <tr key={r.position} className="border-b border-zinc-800/50">
                  <td className="py-1 text-blue-400 font-mono">{r.position}</td>
                  <td className="py-1 text-white">{r.driver}</td>
                  <td className="py-1 text-right text-zinc-400 font-mono">
                    {r.total_time_seconds ? formatTime(r.total_time_seconds) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Agent 预测 VS 实际对比 */}
      {has_prediction && (
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="bg-zinc-900/50 rounded p-2">
            <div className="text-zinc-500 text-xs mb-1">Agent 预测</div>
            <div className="text-red-400 text-xs">{String(prediction.recommended_strategy || prediction.predicted_position || "-")}</div>
          </div>
          <div className="bg-zinc-900/50 rounded p-2">
            <div className="text-zinc-500 text-xs mb-1">实际结果</div>
            <div className="text-blue-400 text-xs">
              冠军: {actual.results?.[0]?.driver || "-"}
            </div>
          </div>
        </div>
      )}

      {/* 奖励 */}
      {reward !== undefined && (
        <div className="border-t border-zinc-800 pt-2 mt-2">
          <span className="text-zinc-500 text-xs">RL 奖励: </span>
          <span className={`font-mono font-bold text-sm ${reward > 0 ? "text-green-400" : reward < 0 ? "text-red-400" : "text-zinc-400"}`}>
            {reward > 0 ? "+" : ""}{reward}
          </span>
          {trace_id && <span className="text-zinc-600 text-xs ml-2">轨迹: {trace_id}</span>}
        </div>
      )}
    </div>
  );
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}