"""FastAPI 入口 + SSE 路由。"""

import asyncio
import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .harness.orchestrator import handle_prompt
from .harness.logger import get_logger
from .memory.manager import MemoryManager

logger = get_logger(__name__)

app = FastAPI(title="F1 策略助手")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局记忆管理器（每个会话一个实例）
sessions: dict[str, MemoryManager] = {}


# ---- 请求模型 ----

class ChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    history: list[dict] = []


# ---- 端点 ----

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/traces")
async def list_traces(season: int | None = None):
    """列出已保存的预测轨迹和准确率统计。"""
    from .memory.trace_store import list_traces as _list, compute_accuracy
    return {
        "traces": _list(season),
        "accuracy": compute_accuracy(season),
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """核心端点：接收用户 prompt，SSE 流式返回 Agent 分析结果。"""
    # 获取或创建会话记忆
    session_id = request.session_id or "default"
    if session_id not in sessions:
        sessions[session_id] = MemoryManager()
        sessions[session_id].new_session(session_id)
    memory = sessions[session_id]

    logger.info(f"POST /api/chat session={session_id} prompt={request.prompt[:80]}...")

    async def event_stream():
        try:
            async for event in handle_prompt(
                prompt=request.prompt,
                history=request.history,
                memory=memory,
            ):
                yield _format_sse(event)
        except Exception as e:
            logger.error(f"Error: {e}")
            yield _format_sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
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