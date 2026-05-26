import { useState } from "react";
import { ChatWindow } from "./components/ChatWindow";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSelectSession = (id: string | null) => {
    setSessionId(id);
  };

  const handleSessionCreated = (newId: string) => {
    setSessionId(newId);
    setRefreshKey((k) => k + 1);
  };

  const handleChatComplete = () => {
    // 每次对话完成后刷新 Sidebar，更新时间戳/消息数
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="h-screen flex bg-zinc-950 text-white">
      <Sidebar
        currentSessionId={sessionId}
        onSelectSession={handleSelectSession}
        refreshKey={refreshKey}
      />

      <div className="flex-1 flex flex-col">
        <header className="border-b border-zinc-800 px-4 py-3 flex items-center gap-2 shrink-0 bg-zinc-950">
          <div className="flex items-center gap-2">
            <span className="inline-block w-1 h-5 rounded-sm" style={{ backgroundColor: "#E10600" }} />
            <span className="text-lg">🏎️</span>
            <span className="font-semibold text-sm tracking-wide text-white">F1 策略助手</span>
          </div>
          <span className="text-zinc-600 text-xs ml-auto">Powered by DeepSeek</span>
        </header>

        <main className="flex-1 overflow-hidden">
          <ChatWindow
            sessionId={sessionId}
            onSessionCreated={handleSessionCreated}
            onChatComplete={handleChatComplete}
          />
        </main>
      </div>
    </div>
  );
}