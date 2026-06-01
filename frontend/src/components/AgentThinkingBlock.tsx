import { useState } from "react";

export function AgentThinkingBlock({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);

  if (!text) return null;

  // 内容很短时不做折叠（小于 60 字符也不必藏）
  if (text.length < 60 && !isStreaming) {
    return (
      <div className="mt-1 pl-3 border-l-2 border-zinc-800 text-xs text-zinc-500 whitespace-pre-wrap leading-relaxed italic">
        {text}
      </div>
    );
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="mt-1 text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors flex items-center gap-1 cursor-pointer"
        title="点击查看推理过程"
      >
        <span className="inline-block w-3 h-3 text-center leading-3">+</span>
        <span>{isStreaming ? "思考中..." : `推理过程 (${Math.ceil(text.length / 100)}百字)`}</span>
      </button>
    );
  }

  return (
    <div className="mt-1">
      <button
        onClick={() => setExpanded(false)}
        className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1 cursor-pointer"
      >
        <span className="inline-block w-3 h-3 text-center leading-3">−</span>
        <span>{isStreaming ? "思考中..." : "收起推理过程"}</span>
      </button>
      <div className="mt-1 pl-3 border-l-2 border-zinc-700 text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
        {text}
      </div>
    </div>
  );
}