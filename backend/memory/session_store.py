"""会话持久化存储 — JSON 文件，每个会话一个文件。"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import BASE_DIR

SESSIONS_DIR = BASE_DIR / "data" / "sessions"


def _ensure_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _now_iso() -> str:
    return datetime.now().isoformat()


def generate_session_id() -> str:
    """生成会话 ID。"""
    return f"sess_{uuid.uuid4().hex[:12]}"


def generate_title_from_prompt(prompt: str, max_len: int = 40) -> str:
    """从首句 prompt 生成会话标题（简单截取，去除多余空白）。"""
    cleaned = " ".join(prompt.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len].rstrip() + "..."


def create_session(session_id: str | None = None, title: str = "新对话") -> dict:
    """创建新会话，返回会话元数据。"""
    _ensure_dir()
    sid = session_id or generate_session_id()
    now = _now_iso()
    session = {
        "id": sid,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _save(session)
    return session


def session_exists(session_id: str) -> bool:
    return _session_path(session_id).exists()


def get_session(session_id: str) -> dict | None:
    """读取完整会话（含所有消息）。"""
    path = _session_path(session_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_sessions() -> list[dict]:
    """列出所有会话的摘要（不含消息内容），按更新时间倒序。"""
    _ensure_dir()
    summaries = []
    for filepath in SESSIONS_DIR.glob("sess_*.json"):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            summaries.append({
                "id": data["id"],
                "title": data.get("title", "未命名"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "message_count": len(data.get("messages", [])),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    summaries.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return summaries


def delete_session(session_id: str) -> bool:
    """删除会话文件。"""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def update_title(session_id: str, title: str) -> bool:
    session = get_session(session_id)
    if session is None:
        return False
    session["title"] = title
    session["updated_at"] = _now_iso()
    _save(session)
    return True


def append_message(
    session_id: str,
    role: str,
    content: str,
    agent: str | None = None,
    extra: dict | None = None,
) -> str:
    """向会话追加一条消息。

    Args:
        session_id: 会话 ID
        role: "user" | "assistant" | "system"
        content: 消息正文
        agent: agent 名（assistant 消息才有）
        extra: 附加字段（如 strategy/comparison/dataCard 数据）

    Returns:
        message_id: 消息唯一 ID
    """
    session = get_session(session_id)
    if session is None:
        # 自动创建
        session = create_session(session_id=session_id, title=generate_title_from_prompt(content) if role == "user" else "新对话")

    msg: dict[str, Any] = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "role": role,
        "content": content,
        "timestamp": _now_iso(),
    }
    if agent:
        msg["agent"] = agent
    if extra:
        msg.update(extra)

    session["messages"].append(msg)
    session["updated_at"] = _now_iso()

    # 第一条 user 消息时，如果标题还是默认值，自动生成标题
    if role == "user" and session.get("title") in (None, "新对话", ""):
        session["title"] = generate_title_from_prompt(content)

    _save(session)
    return msg["id"]


def _save(session: dict) -> None:
    _ensure_dir()
    path = _session_path(session["id"])
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def set_feedback(
    session_id: str,
    message_id: str,
    feedback_type: str,  # "like" | "dislike" | None (取消反馈)
) -> bool:
    """设置消息的用户反馈。

    Args:
        session_id: 会话 ID
        message_id: 消息 ID
        feedback_type: "like" | "dislike" | None

    Returns:
        是否成功
    """
    session = get_session(session_id)
    if session is None:
        return False

    for msg in session["messages"]:
        if msg.get("id") == message_id:
            if feedback_type is None:
                msg.pop("feedback", None)
            else:
                msg["feedback"] = {
                    "type": feedback_type,
                    "timestamp": _now_iso(),
                }
            session["updated_at"] = _now_iso()
            _save(session)
            return True

    return False


def get_feedback_stats() -> dict:
    """获取反馈统计（用于 RLHF）。"""
    _ensure_dir()
    total = 0
    likes = 0
    dislikes = 0

    for filepath in SESSIONS_DIR.glob("sess_*.json"):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            for msg in data.get("messages", []):
                if "feedback" in msg:
                    total += 1
                    if msg["feedback"]["type"] == "like":
                        likes += 1
                    elif msg["feedback"]["type"] == "dislike":
                        dislikes += 1
        except (json.JSONDecodeError, KeyError):
            continue

    return {
        "total_feedback": total,
        "likes": likes,
        "dislikes": dislikes,
        "like_rate": round(likes / total, 3) if total > 0 else 0,
    }