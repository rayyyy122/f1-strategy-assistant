import type { StrategyData } from "../types";
import { TireBadge } from "./F1Badges";

export function StrategyCard({ strategy }: { strategy: StrategyData }) {
  const { recommended_strategy, pit_window, predicted_position, predicted_total_time, key_assumptions, risk_factors, alternatives, confidence, reasoning } = strategy;

  // 从策略文本中提取轮胎配方
  const compoundsInStrategy = extractCompounds(recommended_strategy);

  return (
    <div className="rounded-lg p-4 text-sm border bg-gradient-to-br from-red-950/30 to-zinc-950 border-red-600/40">
      <div className="flex items-center justify-between mb-3">
        <div className="font-bold text-base flex items-center gap-2" style={{ color: "#FF1E0D" }}>
          <span>🎯</span>
          <span>策略建议</span>
        </div>
        {compoundsInStrategy.length > 0 && (
          <div className="flex items-center gap-1">
            {compoundsInStrategy.map((c, i) => (
              <TireBadge key={i} compound={c} size="sm" />
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <div className="text-zinc-500 text-xs mb-0.5">推荐策略</div>
          <div className="text-white font-medium leading-snug">{recommended_strategy}</div>
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
          <div className="font-mono font-medium" style={{ color: "#FF1E0D" }}>{(confidence * 100).toFixed(0)}%</div>
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

function extractCompounds(text: string): string[] {
  if (!text) return [];
  const upper = text.toUpperCase();
  const found: string[] = [];
  for (const c of ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]) {
    if (upper.includes(c)) found.push(c);
  }
  // 中文匹配
  const cnMap: Record<string, string> = { "软胎": "SOFT", "中性胎": "MEDIUM", "硬胎": "HARD", "中胎": "MEDIUM" };
  for (const [zh, en] of Object.entries(cnMap)) {
    if (text.includes(zh) && !found.includes(en)) found.push(en);
  }
  return found;
}