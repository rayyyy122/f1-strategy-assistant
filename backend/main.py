"""FastAPI 入口 + SSE 路由。"""

import asyncio
import json
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .harness.orchestrator import handle_prompt
from .harness.logger import get_logger
from .memory.manager import MemoryManager
from .memory import session_store
from .config import FRONTEND_API_KEY

logger = get_logger(__name__)

app = FastAPI(title="F1 策略助手")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 临时允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 鉴权 ----

async def require_api_key(x_api_key: str | None = Header(default=None)):
    """校验 X-API-Key header。若 FRONTEND_API_KEY 未配置则跳过。"""
    if FRONTEND_API_KEY is None:
        return
    if x_api_key != FRONTEND_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def get_client_id(x_client_id: str | None = Header(default=None)) -> str | None:
    """提取 X-Client-Id header，用于会话归属隔离。允许为空（向后兼容）。"""
    return x_client_id



from .harness.orchestrator import handle_prompt
from .harness.logger import get_logger
from .memory.manager import MemoryManager
from .memory import session_store

logger = get_logger(__name__)

app = FastAPI(title="F1 策略助手")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 临时允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 进行中的 MemoryManager 缓存（运行时内存状态，与磁盘 session_store 分开）
memory_cache: dict[str, MemoryManager] = {}


def get_or_create_memory(session_id: str) -> MemoryManager:
    if session_id not in memory_cache:
        m = MemoryManager()
        m.new_session(session_id)
        memory_cache[session_id] = m
    return memory_cache[session_id]


# ---- 请求模型 ----

class ChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    history: list[dict] = []


class CreateSessionRequest(BaseModel):
    title: str | None = None


class UpdateTitleRequest(BaseModel):
    title: str


class FeedbackRequest(BaseModel):
    message_id: str
    feedback_type: str  # "like" | "dislike" | None


# ---- 端点 ----

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/sessions")
async def list_sessions(
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """列出当前用户的会话（按更新时间倒序）。"""
    return {"sessions": session_store.list_sessions(owner_id=client_id)}


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: str,
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """获取会话完整消息历史。仅会话所有者可访问。"""
    session = session_store.get_session(session_id, owner_id=client_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/api/sessions")
async def create_session(
    request: CreateSessionRequest,
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """显式创建新会话（可选，POST /api/chat 也会自动创建）。"""
    session = session_store.create_session(
        title=request.title or "新对话",
        owner_id=client_id,
    )
    return session


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """删除会话。仅会话所有者可删除。"""
    if session_store.delete_session(session_id, owner_id=client_id):
        memory_cache.pop(session_id, None)
        return {"deleted": True, "id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@app.patch("/api/sessions/{session_id}")
async def update_session_title(
    session_id: str,
    request: UpdateTitleRequest,
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """更新会话标题。仅会话所有者可修改。"""
    if session_store.update_title(session_id, request.title, owner_id=client_id):
        return {"updated": True, "id": session_id, "title": request.title}
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/api/sessions/{session_id}/feedback")
async def set_message_feedback(
    session_id: str,
    request: FeedbackRequest,
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """设置消息的用户反馈（点赞/点踩）。仅会话所有者可操作。"""
    if request.feedback_type not in ("like", "dislike", None):
        raise HTTPException(status_code=400, detail="Invalid feedback_type")

    feedback_type = request.feedback_type if request.feedback_type else None
    if session_store.set_feedback(session_id, request.message_id, feedback_type, owner_id=client_id):
        return {"success": True, "feedback_type": feedback_type}
    raise HTTPException(status_code=404, detail="Session or message not found")


@app.get("/api/feedback/stats")
async def get_feedback_stats(_: None = Depends(require_api_key)):
    """获取反馈统计（用于 RLHF）。"""
    return session_store.get_feedback_stats()


@app.get("/api/traces")
async def list_traces(season: int | None = None, _: None = Depends(require_api_key)):
    """列出已保存的预测轨迹和准确率统计。"""
    from .memory.trace_store import list_traces as _list, compute_accuracy
    return {
        "traces": _list(season),
        "accuracy": compute_accuracy(season),
    }


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    _: None = Depends(require_api_key),
    client_id: str | None = Depends(get_client_id),
):
    """核心端点：接收用户 prompt，SSE 流式返回 Agent 分析结果。"""
    # 自动创建或获取会话（校验归属）
    if request.session_id and session_store.get_session(request.session_id, owner_id=client_id):
        session_id = request.session_id
        is_new_session = False
    else:
        new_session = session_store.create_session(
            title=session_store.generate_title_from_prompt(request.prompt),
            owner_id=client_id,
        )
        session_id = new_session["id"]
        is_new_session = True

    memory = get_or_create_memory(session_id)

    logger.info(f"POST /api/chat session={session_id} new={is_new_session} client={client_id} prompt={request.prompt[:80]}...")

    # 立即持久化用户消息
    session_store.append_message(session_id, role="user", content=request.prompt, owner_id=client_id)

    # 收集 assistant 输出，用于持久化
    assistant_text_parts: list[str] = []
    final_strategy: dict | None = None
    final_comparison: dict | None = None
    data_cards: list[dict] = []

    async def event_stream():
        nonlocal final_strategy, final_comparison

        # 首先发送 session_meta，让前端获得 session_id
        meta = {
            "type": "session_meta",
            "session_id": session_id,
            "is_new": is_new_session,
        }
        yield _format_sse(meta)

        try:
            async for event in handle_prompt(
                prompt=request.prompt,
                history=request.history,
                memory=memory,
            ):
                # 记录关键事件
                etype = event.get("type")
                if etype == "agent_text":
                    assistant_text_parts.append(event.get("delta", ""))
                elif etype == "strategy_card":
                    final_strategy = event.get("strategy")
                elif etype == "comparison_card":
                    final_comparison = event.get("comparison")
                elif etype == "data_card":
                    data_cards.append({
                        "card_type": event.get("card_type"),
                        "data": event.get("data"),
                    })

                yield _format_sse(event)

        except Exception as e:
            logger.error(f"Error: {e}")
            yield _format_sse({"type": "error", "message": str(e)})

        finally:
            # 持久化 assistant 消息
            assistant_content = "".join(assistant_text_parts)
            extra: dict = {}
            if data_cards:
                extra["data_cards"] = data_cards
            if final_strategy:
                extra["strategy"] = final_strategy
            if final_comparison:
                extra["comparison"] = final_comparison

            # 日志记录用户实际看到的完整回复内容
            logger.info(
                f"=== USER-FACING RESPONSE (session={session_id}) ===\n"
                f"PROMPT: {request.prompt}\n"
                f"--- ASSISTANT TEXT ({len(assistant_content)} chars) ---\n"
                f"{assistant_content}\n"
                f"--- EXTRAS ---\n"
                f"data_cards: {len(data_cards)}, strategy: {bool(final_strategy)}, comparison: {bool(final_comparison)}\n"
                f"=== END RESPONSE ==="
            )

            try:
                session_store.append_message(
                    session_id,
                    role="assistant",
                    content=assistant_content,
                    extra=extra or None,
                    owner_id=client_id,
                )
            except Exception as e:
                logger.error(f"持久化失败: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _format_sse(event: dict) -> str:
    """格式化为 SSE 消息。"""
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event.get('type', 'message')}\ndata: {data}\n\n"


# ---- 启动入口 ----

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)