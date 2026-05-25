import { useState, useRef, useEffect, useCallback } from "react";
import type { ChatMessage, SSEEvent } from "../types";
import { nextMsgId } from "../types";
import { useSSE } from "../hooks/useSSE";
import { MessageBubble } from "./MessageBubble";

const SESSION_ID = "default";

export function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const { isStreaming, startStream } = useSSE();
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => scrollToBottom(), [messages, scrollToBottom]);

  const handleSend = async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming) return;

    setInput("");

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: nextMsgId(),
      role: "user",
      content: prompt,
    };
    setMessages((prev) => [...prev, userMsg]);

    // 构建历史
    const history = messages
      .filter((m) => m.role === "user" || m.role === "agent")
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    // 启动 SSE 流
    startStream("/api/chat", { prompt, session_id: SESSION_ID, history }, (event: SSEEvent) => {
      handleEvent(event);
    });
  };

  const handleEvent = (event: SSEEvent) => {
    switch (event.type) {
      case "routing":
        setMessages((prev) => [
          ...prev,
          { id: nextMsgId(), role: "system", content: event.message },
        ]);
        break;

      case "progress":
        setMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: "system",
            content: event.message,
            isStreaming: event.step !== "done",
          },
        ]);
        break;

      case "data_card":
        setMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: "agent",
            content: "",
            dataCard: { card_type: event.card_type, data: event.data },
          },
        ]);
        break;

      case "agent_start": {
        const agentMsg: ChatMessage = {
          id: nextMsgId(),
          role: "agent",
          agent: event.agent,
          content: "",
          thinking: "",
          isStreaming: true,
        };
        setMessages((prev) => [...prev, agentMsg]);
        break;
      }

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

      case "agent_complete":
        setMessages((prev) =>
          prev.map((m) =>
            m.agent === event.agent && m.isStreaming
              ? { ...m, isStreaming: false }
              : m,
          ),
        );
        break;

      case "strategy_card":
        setMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: "agent",
            content: "",
            strategy: event.strategy,
          },
        ]);
        break;

      case "comparison_card":
        setMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: "agent",
            content: "",
            comparison: event.comparison,
          },
        ]);
        break;

      case "complete":
        // 追加完成状态
        setMessages((prev) => [
          ...prev,
          {
            id: nextMsgId(),
            role: "system",
            content: event.elapsed_s ? `分析完成 · ${event.elapsed_s}s` : "分析完成",
          },
        ]);
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

  return (
    <div className="flex flex-col h-full bg-zinc-950">
      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-600">
            <div className="text-4xl mb-4">🏎️</div>
            <div className="text-lg font-medium mb-2 text-zinc-500">F1 策略助手</div>
            <div className="text-sm text-zinc-700 max-w-xs text-center leading-relaxed">
              输入你的 F1 策略问题，例如：<br />
              "分析2024摩纳哥大奖赛的轮胎策略"
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* 输入框 */}
      <div className="border-t border-zinc-800 p-4 bg-zinc-950">
        <div className="flex gap-2 max-w-3xl mx-auto">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的 F1 策略问题..."
            disabled={isStreaming}
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-amber-600/50 transition-colors disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            className="bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-600 text-black font-medium px-5 py-3 rounded-xl text-sm transition-colors"
          >
            {isStreaming ? "..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}