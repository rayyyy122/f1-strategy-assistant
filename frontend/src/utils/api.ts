import type { ChatRequest, SessionSummary, SessionDetail } from "../types";

// 后端地址：优先读环境变量，否则回退到本地开发
export const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api";

// 前端访问密钥（用于防止 /api 被公网蹭用；与后端 FRONTEND_API_KEY 保持一致）
export const FRONTEND_API_KEY = "o1c2iHuutraOhIHT5DyOMJaA39hTR6gG";

// ---- Client ID（浏览器级匿名身份，用于会话隔离） ----

const CLIENT_ID_KEY = "f1_client_id";

export function getClientId(): string {
  let id = localStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = `client_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
    localStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

export const AUTH_HEADERS: Record<string, string> = {
  "X-API-Key": FRONTEND_API_KEY,
  "X-Client-Id": getClientId(),
};

function jsonHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", ...AUTH_HEADERS };
}

export async function postChat(request: ChatRequest): Promise<Response> {
  return fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: jsonHeaders(),
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
  const res = await fetch(`${API_BASE}/sessions`, { headers: AUTH_HEADERS });
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  const data = await res.json();
  return data.sessions;
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, { headers: AUTH_HEADERS });
  if (!res.ok) throw new Error(`Failed to get session: ${res.status}`);
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "DELETE",
    headers: AUTH_HEADERS,
  });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.status}`);
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Failed to update title: ${res.status}`);
}

// ---- Feedback API ----

export async function setFeedback(
  sessionId: string,
  messageId: string,
  feedbackType: "like" | "dislike" | null,
): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/feedback`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ message_id: messageId, feedback_type: feedbackType }),
  });
  if (!res.ok) throw new Error(`Failed to set feedback: ${res.status}`);
}

export async function getFeedbackStats(): Promise<{
  total_feedback: number;
  likes: number;
  dislikes: number;
  like_rate: number;
}> {
  const res = await fetch(`${API_BASE}/feedback/stats`, { headers: AUTH_HEADERS });
  if (!res.ok) throw new Error(`Failed to get feedback stats: ${res.status}`);
  return res.json();
}