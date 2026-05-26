import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, ChevronRight, ChevronDown, Wrench } from "lucide-react";
import type { ChatMessage, ToolActivity } from "../types";
import { DataCard } from "./DataCard";
import { AgentThinkingBlock } from "./AgentThinkingBlock";
import { StrategyCard } from "./StrategyCard";
import { ComparisonCard } from "./ComparisonCard";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const { role, agent, content, thinking, isStreaming, dataCard, strategy, comparison, toolActivity } = message;

  // 系统消息（居中灰色）
  if (role === "system") {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-zinc-500 bg-zinc-950/50 px-3 py-1 rounded-full">
          {isStreaming && <span className="inline-block w-2 h-2 bg-red-500 rounded-full animate-pulse mr-1.5 align-middle" />}
          {content}
        </span>
      </div>
    );
  }

  // 用户消息（右对齐）
  if (role === "user") {
    return (
      <div className="flex justify-end my-3">
        <div
          className="text-white rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%] text-sm leading-relaxed whitespace-pre-wrap"
          style={{ backgroundColor: "#E10600" }}
        >
          {content}
        </div>
      </div>
    );
  }

  // Agent 消息（左对齐）
  return (
    <div className="flex flex-col my-3">
      {/* 数据卡片 */}
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
      {(agent || content || thinking || (toolActivity && toolActivity.length > 0)) && (
        <div className="max-w-[85%] group">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl rounded-bl-md px-4 py-2.5 relative">
            {agent && (
              <div className="text-xs text-zinc-500 mb-1 font-medium flex items-center gap-1">
                <AgentBadge agent={agent} />
                {isStreaming && <span className="text-red-500 ml-1 animate-pulse">...</span>}
              </div>
            )}
            <AgentThinkingBlock text={thinking || ""} isStreaming={isStreaming && !content} />
            {toolActivity && toolActivity.length > 0 && (
              <ToolActivityBlock activity={toolActivity} isStreaming={isStreaming} />
            )}
            {content && <MarkdownContent text={content} isStreaming={isStreaming} />}
            {content && !isStreaming && (
              <CopyButton text={content} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ToolActivityBlock({ activity, isStreaming }: { activity: ToolActivity[]; isStreaming?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const inProgress = activity.some((a) => a.status === "calling");
  const label = inProgress ? "执行中..." : `执行了 ${activity.length} 步`;

  return (
    <div className="my-1.5 bg-zinc-950/40 border border-zinc-800 rounded-md overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Wrench size={11} className={inProgress ? "text-red-500 animate-pulse" : "text-zinc-500"} />
        <span>{label}</span>
        {isStreaming && inProgress && (
          <span className="ml-auto text-red-500 animate-pulse">●</span>
        )}
      </button>
      {expanded && (
        <div className="px-3 pb-2 pt-1 space-y-2 border-t border-zinc-800">
          {activity.map((a, i) => (
            <div key={i} className="text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className={`font-mono ${a.status === "done" ? "text-emerald-400" : "text-amber-400"}`}>
                  {a.status === "done" ? "✓" : "▶"}
                </span>
                <span className="text-zinc-300 font-medium">{a.tool}</span>
              </div>
              {a.params != null && (
                <div className="ml-4 mt-0.5 text-zinc-500">
                  参数: <code className="text-zinc-400 break-all">{truncateJSON(a.params)}</code>
                </div>
              )}
              {a.result != null && a.status === "done" && (
                <div className="ml-4 mt-0.5 text-zinc-500">
                  结果: <code className="text-zinc-400 break-all">{truncateJSON(a.result)}</code>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function truncateJSON(value: unknown, maxLen: number = 200): string {
  let s: string;
  try {
    s = typeof value === "string" ? value : JSON.stringify(value);
  } catch {
    s = String(value);
  }
  if (s.length > maxLen) return s.slice(0, maxLen) + "...";
  return s;
}

function AgentBadge({ agent }: { agent: string }) {
  const badges: Record<string, { icon: string; label: string; color: string }> = {
    race_context: { icon: "🏁", label: "Race Context", color: "text-zinc-400" },
    tire_strategist: { icon: "🛞", label: "Tire Strategist", color: "text-emerald-400" },
    competitor_analyst: { icon: "🏎️", label: "Competitor Analyst", color: "text-purple-400" },
    synthesis: { icon: "🎯", label: "Synthesis", color: "text-red-500" },
  };
  const badge = badges[agent] || { icon: "🤖", label: agent, color: "text-zinc-400" };
  return (
    <span className={badge.color}>
      {badge.icon} {badge.label}
    </span>
  );
}

function MarkdownContent({ text, isStreaming }: { text: string; isStreaming?: boolean }) {
  return (
    <div className="text-sm text-zinc-200 leading-relaxed markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-1 leading-relaxed">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
          em: ({ children }) => <em className="italic text-zinc-300">{children}</em>,
          ul: ({ children }) => <ul className="list-disc list-inside my-1.5 space-y-0.5 pl-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-inside my-1.5 space-y-0.5 pl-1">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          h1: ({ children }) => <h1 className="text-base font-bold text-white mt-3 mb-1.5">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold text-white mt-2.5 mb-1">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold text-zinc-100 mt-2 mb-1">{children}</h3>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-red-400 hover:text-red-300 underline underline-offset-2">
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            const isInline = !className;
            if (isInline) {
              return <code className="bg-zinc-800 text-red-300 px-1.5 py-0.5 rounded text-[0.8em] font-mono">{children}</code>;
            }
            return (
              <code className="block bg-zinc-950 border border-zinc-800 text-zinc-200 p-3 rounded-lg my-2 text-xs font-mono overflow-x-auto">
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="my-2 overflow-x-auto">{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-zinc-700 pl-3 my-2 text-zinc-400 italic">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border border-zinc-800 px-2 py-1 bg-zinc-900 text-zinc-300 text-left">{children}</th>,
          td: ({ children }) => <td className="border border-zinc-800 px-2 py-1 text-zinc-300">{children}</td>,
          hr: () => <hr className="border-zinc-800 my-3" />,
        }}
      >
        {text}
      </ReactMarkdown>
      {isStreaming && <span className="text-red-500 animate-pulse ml-0.5">▌</span>}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 忽略复制失败
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute -top-2 -right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md p-1.5 text-zinc-400 hover:text-white"
      title={copied ? "已复制" : "复制"}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
}