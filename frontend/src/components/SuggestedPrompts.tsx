import { Sparkles } from "lucide-react";

const SUGGESTIONS = [
  {
    title: "赛前策略分析",
    prompt: "分析 2024 摩纳哥大奖赛的轮胎策略",
    hint: "完整 4 Agent 流程",
  },
  {
    title: "赛后复盘",
    prompt: "复盘 2025 银石大奖赛的预测和实际结果",
    hint: "对比 Agent 预测 vs 真实结果",
  },
  {
    title: "赛道信息查询",
    prompt: "西班牙赛道有什么特点？",
    hint: "快速回答",
  },
  {
    title: "F1 知识问答",
    prompt: "什么是 DRS？什么时候可以使用？",
    hint: "通用问题",
  },
];

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void;
}

export function SuggestedPrompts({ onSelect }: SuggestedPromptsProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-zinc-600 px-6">
      <div className="text-5xl mb-3">🏎️</div>
      <div className="text-xl font-medium mb-1 text-zinc-300">F1 策略助手</div>
      <div className="text-sm text-zinc-600 mb-8 text-center">
        基于真实 F1 数据的多 Agent 策略分析
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl w-full">
        {SUGGESTIONS.map((s, i) => (
          <button
            key={i}
            onClick={() => onSelect(s.prompt)}
            className="group text-left p-4 bg-zinc-900/60 hover:bg-zinc-800/80 border border-zinc-800 hover:border-red-600/40 rounded-xl transition-all duration-200"
          >
            <div className="flex items-start gap-2 mb-1.5">
              <Sparkles size={14} className="text-red-500 mt-0.5 shrink-0" />
              <div className="text-sm font-medium text-zinc-200 group-hover:text-white">
                {s.title}
              </div>
            </div>
            <div className="text-xs text-zinc-400 leading-relaxed pl-6">
              {s.prompt}
            </div>
            <div className="text-[10px] text-zinc-600 mt-1.5 pl-6">{s.hint}</div>
          </button>
        ))}
      </div>
    </div>
  );
}