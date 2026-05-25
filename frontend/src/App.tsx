import { ChatWindow } from "./components/ChatWindow";

export default function App() {
  return (
    <div className="h-screen flex flex-col bg-zinc-950 text-white">
      {/* 顶部栏 */}
      <header className="border-b border-zinc-800 px-4 py-3 flex items-center gap-2 shrink-0">
        <span className="text-lg">🏎️</span>
        <span className="font-semibold text-sm tracking-wide">F1 策略助手</span>
        <span className="text-zinc-600 text-xs ml-auto">Powered by Claude</span>
      </header>

      {/* 对话框主体 */}
      <main className="flex-1 overflow-hidden">
        <ChatWindow />
      </main>
    </div>
  );
}