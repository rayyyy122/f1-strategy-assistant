import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Square, ArrowDown, RotateCcw } from "lucide-react";
import type { ChatMessage, SSEEvent, StoredMessage } from "../types";
import { nextMsgId } from "../types";
import { useSSE } from "../hooks/useSSE";
import { MessageBubble } from "./MessageBubble";
import { SuggestedPrompts } from "./SuggestedPrompts";
import { getSession } from "../utils/api";

interface ChatWindowProps {
  sessionId: string | null;
  onSessionCreated?: (newId: string) => void;
  onChatComplete?: () => void;
}

export function ChatWindow({ sessionId, onSessionCreated, onChatComplete }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [lastUsage, setLastUsage] = useState<{ in: number; out: number } | null>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const { isStreaming, startStream, stopStream } = useSSE();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 跟踪 ChatWindow 已知的 sessionId（避免 session_meta 触发的 prop 变化重新加载历史）
  const knownSessionIdRef = useRef<string | null>(null);

  // 加载历史（仅外部切换，如 Sidebar 点击；本会话流式创建的 sessionId 跳过）
  useEffect(() => {
    if (sessionId === knownSessionIdRef.current) return;

    if (!sessionId) {
      knownSessionIdRef.current = null;
      setMessages([]);
      setLastUsage(null);
      return;
    }
    knownSessionIdRef.current = sessionId;
    let mounted = true;
    setLoadingHistory(true);
    getSession(sessionId)
      .then((session) => {
        if (!mounted) return;
        setMessages(session.messages.flatMap(storedToChatMessages));
      })
      .catch((err) => {
        console.error("加载会话失败", err);
        if (mounted) setMessages([]);
      })
      .finally(() => {
        if (mounted) setLoadingHistory(false);
      });
    return () => {
      mounted = false;
    };
  }, [sessionId]);

  // 滚动到底部（只滚动消息列表容器，不影响外层布局）
  const scrollToBottom = useCallback((smooth = true) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }, []);

  // 监听滚动位置
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsAtBottom(distanceFromBottom < 80);
  }, []);

  // 仅当用户在底部时才自动滚
  useEffect(() => {
    if (isAtBottom) scrollToBottom(true);
  }, [messages, isAtBottom, scrollToBottom]);

  // 自动撑高 textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [input]);

  const sendPrompt = (prompt: string, dropAfter?: number) => {
    if (!prompt.trim() || isStreaming) return;

    setInput("");
    setLastUsage(null);

    // dropAfter: 重新生成时丢弃指定索引之后的消息
    setMessages((prev) => {
      const base = dropAfter !== undefined ? prev.slice(0, dropAfter) : prev;
      return [...base, { id: nextMsgId(), role: "user", content: prompt }];
    });

    // 强制滚动到底部（用户主动操作）
    setIsAtBottom(true);

    const history = messages
      .filter((m) => m.role === "user" || m.role === "agent")
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    const body: { prompt: string; session_id?: string; history: typeof history } = {
      prompt,
      history,
    };
    if (sessionId) body.session_id = sessionId;

    startStream("/api/chat", body, (event: SSEEvent) => {
      handleEvent(event);
    });
  };

  const handleSend = () => sendPrompt(input.trim());

  const handleStop = () => {
    stopStream();
    setMessages((prev) => [
      ...prev,
      { id: nextMsgId(), role: "system", content: "已停止生成" },
    ]);
  };

  // 重新生成：找到最后一条用户消息，丢弃之后的内容并重新发送
  const handleRegenerate = () => {
    if (isStreaming) return;
    let lastUserIdx = -1;
    let lastUserPrompt = "";
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserIdx = i;
        lastUserPrompt = messages[i].content;
        break;
      }
    }
    if (lastUserIdx < 0) return;
    sendPrompt(lastUserPrompt, lastUserIdx);
  };

  const handleEvent = (event: SSEEvent) => {
    switch (event.type) {
      case "session_meta":
        if (event.is_new) {
          // 先标记 ref，避免 prop 变化触发的 useEffect 重载历史
          knownSessionIdRef.current = event.session_id;
          if (onSessionCreated) onSessionCreated(event.session_id);
        }
        break;

      case "routing":
        setMessages((prev) => [...prev, { id: nextMsgId(), role: "system", content: event.message }]);
        break;

      case "progress":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "system", content: event.message, isStreaming: event.step !== "done" },
        ]);
        break;

      case "data_card":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "agent", content: "", dataCard: { card_type: event.card_type, data: event.data } },
        ]);
        break;

      case "agent_start":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "agent", agent: event.agent, content: "", thinking: "", isStreaming: true, toolActivity: [] },
        ]);
        break;

      case "agent_thinking":
        setMessages((prev) =>
          prev.map((m) =>
            m.isStreaming && m.agent === event.agent
              ? { ...m, thinking: (m.thinking || "") + event.delta }
              : m,
          ),
        );
        break;

      case "agent_text":
        setMessages((prev) =>
          prev.map((m) =>
            m.isStreaming && m.agent === event.agent
              ? { ...m, content: (m.content || "") + event.delta }
              : m,
          ),
        );
        break;

      case "agent_tool_call":
        setMessages((prev) =>
          prev.map((m) => {
            if (!(m.isStreaming && m.agent === event.agent)) return m;
            const activity = [...(m.toolActivity || []), {
              tool: event.tool,
              params: event.params,
              status: "calling" as const,
            }];
            return { ...m, toolActivity: activity };
          }),
        );
        break;

      case "agent_tool_result":
        setMessages((prev) =>
          prev.map((m) => {
            if (!(m.isStreaming && m.agent === event.agent)) return m;
            const activity = [...(m.toolActivity || [])];
            // 找最后一个同名 tool 的 calling 项标为 done
            for (let i = activity.length - 1; i >= 0; i--) {
              if (activity[i].tool === event.tool && activity[i].status === "calling") {
                activity[i] = { ...activity[i], result: event.result, status: "done" };
                break;
              }
            }
            return { ...m, toolActivity: activity };
          }),
        );
        break;

      case "agent_complete":
        setMessages((prev) =>
          prev.map((m) =>
            m.agent === event.agent && m.isStreaming ? { ...m, isStreaming: false } : m,
          ),
        );
        break;

      case "strategy_card":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "agent", content: "", strategy: event.strategy },
        ]);
        break;

      case "comparison_card":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "agent", content: "", comparison: event.comparison },
        ]);
        break;

      case "complete":
        setMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: "system",
            content: event.elapsed_s ? `分析完成 · ${event.elapsed_s}s` : "分析完成",
          },
        ]);
        if (event.usage) {
          setLastUsage({
            in: event.usage.input_tokens || 0,
            out: event.usage.output_tokens || 0,
          });
        }
        if (onChatComplete) onChatComplete();
        break;

      case "error":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "system", content: `错误: ${event.message}` },
        ]);
        break;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const showEmpty = !loadingHistory && messages.length === 0;

  // 是否可以重新生成（最后一条非用户消息且不在 streaming）
  const canRegenerate =
    !isStreaming &&
    messages.length > 0 &&
    messages.some((m) => m.role === "user");

  return (
    <div className="flex flex-col h-full bg-zinc-950 relative">
      {/* 消息列表 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-4"
      >
        <div className="max-w-3xl mx-auto space-y-1">
          {loadingHistory && (
            <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
              加载历史消息...
            </div>
          )}
          {showEmpty && <SuggestedPrompts onSelect={sendPrompt} />}
          {!loadingHistory && messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* 浮动"回到底部"按钮 */}
      {!isAtBottom && (
        <button
          onClick={() => {
            setIsAtBottom(true);
            scrollToBottom(true);
          }}
          className="absolute bottom-28 right-6 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-full p-2 shadow-lg text-zinc-300 hover:text-white transition-all"
          title="回到底部"
        >
          <ArrowDown size={18} />
        </button>
      )}

      {/* 工具栏：重新生成 + token 用量 */}
      {(canRegenerate || lastUsage) && !showEmpty && (
        <div className="border-t border-zinc-900 py-1.5 bg-zinc-950 text-xs">
          <div className="max-w-3xl mx-auto px-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              {canRegenerate && (
                <button
                  onClick={handleRegenerate}
                  className="flex items-center gap-1 text-zinc-500 hover:text-zinc-200 transition-colors"
                  title="重新生成最后一次回复"
                >
                  <RotateCcw size={12} />
                  <span>重新生成</span>
                </button>
              )}
            </div>
            {lastUsage && (
              <span className="text-zinc-600">
                Tokens · 输入 {lastUsage.in.toLocaleString()} / 输出 {lastUsage.out.toLocaleString()}
              </span>
            )}
          </div>
        </div>
      )}

      {/* 输入框 */}
      <div className="border-t border-zinc-800 p-4 bg-zinc-950">
        <div className="flex gap-2 max-w-3xl mx-auto items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的 F1 策略问题... (Shift+Enter 换行)"
            disabled={isStreaming}
            rows={1}
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-red-600/60 transition-colors disabled:opacity-50 resize-none overflow-y-auto leading-relaxed"
            style={{ minHeight: "48px" }}
          />
          {isStreaming ? (
            <button
              onClick={handleStop}
              className="bg-red-500/90 hover:bg-red-500 text-white font-medium px-4 py-3 rounded-xl text-sm transition-colors flex items-center gap-1.5 shrink-0"
              title="停止生成"
            >
              <Square size={14} fill="currentColor" />
              <span>停止</span>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="text-white font-medium px-4 py-3 rounded-xl text-sm transition-all flex items-center gap-1.5 shrink-0 disabled:bg-zinc-800 disabled:text-zinc-600 disabled:cursor-not-allowed enabled:hover:brightness-110"
              style={{
                backgroundColor: input.trim() ? "#E10600" : undefined,
              }}
              title="发送 (Enter)"
            >
              <Send size={14} />
              <span>发送</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** 把后端持久化的 StoredMessage 还原为前端展示的 ChatMessage 列表。 */
function storedToChatMessages(stored: StoredMessage): ChatMessage[] {
  if (stored.role === "user") {
    return [{ id: nextMsgId(), role: "user", content: stored.content }];
  }

  const result: ChatMessage[] = [];

  if (stored.data_cards && stored.data_cards.length > 0) {
    for (const card of stored.data_cards) {
      result.push({ id: nextMsgId(), role: "agent", content: "", dataCard: card });
    }
  }

  if (stored.content) {
    result.push({
      id: nextMsgId(),
      role: "agent",
      agent: stored.agent || "synthesis",
      content: stored.content,
    });
  }

  if (stored.strategy) {
    result.push({ id: nextMsgId(), role: "agent", content: "", strategy: stored.strategy });
  }

  if (stored.comparison) {
    result.push({ id: nextMsgId(), role: "agent", content: "", comparison: stored.comparison });
  }

  return result;
}