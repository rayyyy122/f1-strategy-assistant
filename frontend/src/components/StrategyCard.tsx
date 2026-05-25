import type { StrategyData } from "../types";

export function StrategyCard({ strategy }: { strategy: StrategyData }) {
  const { recommended_strategy, pit_window, predicted_position, predicted_total_time, key_assumptions, risk_factors, alternatives, confidence, reasoning } = strategy;

  return (
    <div className="bg-amber-950/20 border border-amber-600/30 rounded-lg p-4 text-sm">
      <div className="text-amber-400 font-bold mb-3 text-base">策略建议</div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <div className="text-zinc-500 text-xs mb-0.5">推荐策略</div>
          <div className="text-white font-medium">{recommended_strategy}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs mb-0.5">进站窗口</div>
          <div className="text-white font-medium">{pit_window}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs mb-0.5">预测完赛</div>
          <div className="text-white font-medium">{predicted_position}{predicted_total_time ? ` · ${predicted_total_time}` : ""}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs mb-0.5">置信度</div>
          <div className="text-amber-400 font-mono font-medium">{(confidence * 100).toFixed(0)}%</div>
        </div>
      </div>

      {key_assumptions.length > 0 && (
        <div className="mb-2">
          <div className="text-zinc-500 text-xs mb-1">关键假设</div>
          <ul className="text-zinc-300 text-xs space-y-0.5">
            {key_assumptions.map((a, i) => <li key={i}>· {a}</li>)}
          </ul>
        </div>
      )}

      {risk_factors.length > 0 && (
        <div className="mb-2">
          <div className="text-zinc-500 text-xs mb-1">风险因子</div>
          {risk_factors.map((r, i) => (
            <div key={i} className="text-xs mb-1">
              <span className="text-red-400">{r.risk}</span>
              <span className="text-zinc-500"> ({r.probability})</span>
              <span className="text-zinc-400"> — {r.impact}</span>
            </div>
          ))}
        </div>
      )}

      {alternatives.length > 0 && (
        <div className="mb-2">
          <div className="text-zinc-500 text-xs mb-1">备选方案</div>
          {alternatives.map((a, i) => (
            <div key={i} className="text-zinc-400 text-xs">· {a}</div>
          ))}
        </div>
      )}

      {reasoning && (
        <div className="border-t border-zinc-800 pt-2 mt-2">
          <div className="text-zinc-500 text-xs mb-1">推理过程</div>
          <div className="text-zinc-400 text-xs leading-relaxed">{reasoning}</div>
        </div>
      )}
    </div>
  );
}