import { useEffect, useState } from "react";
import type { SessionSummary } from "../types";
import { listSessions, deleteSession } from "../utils/api";

interface SidebarProps {
  currentSessionId: string | null;
  onSelectSession: (id: string | null) => void;
  refreshKey?: number;
}

export function Sidebar({ currentSessionId, onSelectSession, refreshKey }: SidebarProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    listSessions()
      .then((data) => {
        if (mounted) setSessions(data);
      })
      .catch(() => {})
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [refreshKey]);

  const handleNew = () => onSelectSession(null);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm("删除此会话？")) return;
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) onSelectSession(null);
    } catch (err) {
      console.error(err);
    }
  };

  if (collapsed) {
    return (
      <div className="w-12 bg-zinc-950 border-r border-zinc-900 flex flex-col items-center py-3 gap-3">
        <button
          onClick={() => setCollapsed(false)}
          title="展开侧栏"
          className="text-zinc-500 hover:text-white p-2 rounded transition-colors"
        >
          ☰
        </button>
        <button
          onClick={handleNew}
          title="新对话"
          className="text-red-500 hover:text-red-400 p-2 rounded transition-colors text-lg leading-none"
        >
          +
        </button>
      </div>
    );
  }

  return (
    <aside className="w-64 bg-zinc-950 border-r border-zinc-900 flex flex-col shrink-0">
      <div className="p-3 border-b border-zinc-900 flex items-center gap-2">
        <button
          onClick={handleNew}
          className="flex-1 flex items-center gap-2 px-3 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg text-sm text-zinc-200 transition-colors"
        >
          <span className="text-red-500">+</span>
          <span>新对话</span>
        </button>
        <button
          onClick={() => setCollapsed(true)}
          title="折叠侧栏"
          className="text-zinc-500 hover:text-white p-2 rounded transition-colors"
        >
          «
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading && <div className="text-zinc-600 text-xs px-2 py-3">加载中...</div>}
        {!loading && sessions.length === 0 && (
          <div className="text-zinc-700 text-xs px-2 py-6 text-center leading-relaxed">
            还没有对话<br />
            点击"+ 新对话"开始
          </div>
        )}
        {sessions.map((s) => {
          const active = s.id === currentSessionId;
          return (
            <div
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors ${
                active
                  ? "bg-zinc-800/70 text-white"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
              }`}
            >
              <span className="flex-1 truncate" title={s.title}>{s.title}</span>
              <button
                onClick={(e) => handleDelete(e, s.id)}
                className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-opacity"
                title="删除会话"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>

      <div className="p-3 border-t border-zinc-900 text-xs text-zinc-600">
        {sessions.length > 0 && <span>{sessions.length} 个对话</span>}
      </div>
    </aside>
  );
}