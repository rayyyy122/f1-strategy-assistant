import { useState } from "react";

export function AgentThinkingBlock({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);

  if (!text) return null;

  return (
    <div className="mt-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        <span>推理过程{isStreaming ? "..." : ""}</span>
      </button>
      {expanded && (
        <div className="mt-1 pl-4 border-l-2 border-zinc-700 text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
          {text}
        </div>
      )}
    </div>
  );
}