import type { ChatRequest, SessionSummary, SessionDetail } from "../types";

const API_BASE = "/api";

export async function postChat(request: ChatRequest): Promise<Response> {
  return fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// ---- Sessions API ----

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  const data = await res.json();
  return data.sessions;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to get session: ${res.status}`);
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.status}`);
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Failed to update title: ${res.status}`);
}