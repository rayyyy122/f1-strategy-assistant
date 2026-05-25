import type { ChatMessage } from "../types";
import { DataCard } from "./DataCard";
import { AgentThinkingBlock } from "./AgentThinkingBlock";
import { StrategyCard } from "./StrategyCard";
import { ComparisonCard } from "./ComparisonCard";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const { role, agent, content, thinking, isStreaming, dataCard, strategy, comparison } = message;

  // 系统消息（居中灰色）
  if (role === "system") {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-zinc-500 bg-zinc-950/50 px-3 py-1 rounded-full">
          {isStreaming && <span className="inline-block w-2 h-2 bg-amber-400 rounded-full animate-pulse mr-1.5 align-middle" />}
          {content}
        </span>
      </div>
    );
  }

  // 用户消息（右对齐）
  if (role === "user") {
    return (
      <div className="flex justify-end my-3">
        <div className="bg-zinc-800 text-white rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%] text-sm leading-relaxed">
          {content}
        </div>
      </div>
    );
  }

  // Agent 消息（左对齐）
  return (
    <div className="flex flex-col my-3">
      {/* 数据卡片（在 Agent 气泡之前） */}
      {dataCard && (
        <div className="mb-2 max-w-[85%]">
          <DataCard cardType={dataCard.card_type} data={dataCard.data} />
        </div>
      )}

      {/* 策略卡片 */}
      {strategy && (
        <div className="mb-2 max-w-[90%]">
          <StrategyCard strategy={strategy} />
        </div>
      )}

      {/* 复盘对比卡片 */}
      {comparison && (
        <div className="mb-2 max-w-[90%]">
          <ComparisonCard comparison={comparison} />
        </div>
      )}

      {/* Agent 气泡 */}
      <div className="max-w-[85%]">
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl rounded-bl-md px-4 py-2.5">
          {agent && (
            <div className="text-xs text-zinc-500 mb-1 font-medium">
              {agent === "race_context" && "🏁 Race Context"}
              {agent === "tire_strategist" && "🛞 Tire Strategist"}
              {agent === "competitor_analyst" && "🏎️ Competitor Analyst"}
              {agent === "synthesis" && "🎯 Synthesis"}
              {isStreaming && <span className="text-amber-400 ml-1 animate-pulse">...</span>}
            </div>
          )}
          <AgentThinkingBlock text={thinking || ""} isStreaming={isStreaming && !content} />
          {content && (
            <div className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap">
              {content}
              {isStreaming && <span className="text-amber-400 animate-pulse ml-0.5">▌</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}