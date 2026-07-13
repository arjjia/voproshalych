"""FastAPI приложение agent-service.

Эндпоинты:
- POST /chat — синхронный чат (JSON)
- GET  /chat/stream — стриминг SSE
- GET  /v1/models — список моделей (OpenAI-совместимый)
- POST /v1/chat/completions — чат (OpenAI-совместимый)
- GET  /health — healthcheck
- GET  /mcp/tools — список доступных инструментов
- GET  /trace — получить трассировку по request_id
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .graph import build_graph
from .middleware import UserIdentityMiddleware
from .models import AgentState, Intent, Profile
from .mcp_client import MCPClient
from .streaming import stream_agent_events
from .trace_logger import get_traces

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str
    user_id: str = "anonymous"
    role: str = "guest"
    dialog_context: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict[str, str]] | None = None
    intent: str | None = None
    dialog_context: str = ""
    error: str | None = None


graph = build_graph()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("agent-service starting...")
    logger.info(f"LiteLLM: {settings.litellm_url}")
    logger.info(f"Model: {settings.llm_model}")
    logger.info(f"MCP servers: kb={settings.mcp_kb_url}, news={settings.mcp_news_url}")
    yield
    logger.info("agent-service shutting down...")


app = FastAPI(title="Voproshalych v3 Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(UserIdentityMiddleware)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """Основной эндпоинт чата."""
    logger.info(f"chat: query={req.query!r}, user={req.user_id}, role={req.role}")

    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    profile = Profile(
        user_id=req.user_id or getattr(request.state, "user_id", "anonymous"),
        role=req.role or getattr(request.state, "role", "guest"),
    )

    state = AgentState(
        messages=[{"role": "user", "content": req.query}],
        dialog_context=req.dialog_context,
        profile=profile,
        request_id=request_id,
    )

    try:
        result = await graph.ainvoke(state)
        if isinstance(result, dict):
            raw = result
        else:
            raw = {
                "final_answer": result.final_answer,
                "sources": result.sources,
                "intent": result.intent.value if result.intent else None,
                "error": result.error,
                "dialog_context": result.dialog_context,
            }
        new_context = raw.get("dialog_context") or req.dialog_context or ""
        if req.query and raw.get("final_answer"):
            new_pair = f"Пользователь: {req.query}\nВопрошалыч: {raw['final_answer']}\n"
            new_context = (new_context + "\n" + new_pair).strip()
            # keep last ~2000 chars
            if len(new_context) > 2000:
                new_context = new_context[-2000:]
        return ChatResponse(
            answer=raw.get("final_answer") or "Не удалось обработать запрос.",
            sources=raw.get("sources") or [],
            intent=raw.get("intent"),
            dialog_context=new_context,
            error=raw.get("error"),
        )
    except Exception as e:
        logger.error(f"chat error: {e}")
        return ChatResponse(
            answer="Произошла внутренняя ошибка. Попробуйте позже.",
            error=str(e),
        )


@app.get("/chat/stream")
async def chat_stream(
    query: str,
    user_id: str = "anonymous",
    role: str = "guest",
    request: Request = None,
):
    """Стриминг ответа агента через SSE."""
    logger.info(f"chat_stream: query={query!r}, user={user_id}")

    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    request_id = getattr(request.state, "request_id", str(uuid.uuid4())) if request else str(uuid.uuid4())
    profile = Profile(
        user_id=user_id or getattr(request.state, "user_id", "anonymous") if request else user_id,
        role=role or getattr(request.state, "role", "guest") if request else role,
    )

    state = AgentState(
        messages=[{"role": "user", "content": query}],
        profile=profile,
        request_id=request_id,
    )

    try:
        result = await graph.ainvoke(state)
    except Exception as e:
        logger.error(f"chat_stream error: {e}")
        return EventSourceResponse(
            _error_stream(str(e))
        )

    if isinstance(result, dict):
        state.final_answer = result.get("final_answer")
        state.sources = result.get("sources")
        intent_val = result.get("intent")
        state.intent = Intent(intent_val) if intent_val else None
        state.error = result.get("error")
    else:
        state.final_answer = result.final_answer
        state.sources = result.sources
        state.intent = result.intent
        state.error = result.error

    return EventSourceResponse(stream_agent_events(state))


async def _error_stream(error_msg: str):
    yield f"event: error\ndata: {error_msg}\n\n"
    yield "event: done\ndata: {}\n\n"


# ── OpenAI-совместимые эндпоинты для Open WebUI ──


class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIRequest(BaseModel):
    model: str = "voproshalych-v3"
    messages: list[OpenAIMessage]
    stream: bool = False
    temperature: float | None = 0.7
    max_tokens: int | None = 2048


class OpenAICompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@app.get("/v1/models")
async def openai_models():
    """Список доступных моделей (OpenAI-совместимый)."""
    return {
        "object": "list",
        "data": [
            {
                "id": settings.llm_model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "voproshalych",
            },
        ],
    }


@app.post("/v1/embeddings")
async def openai_embeddings(request: Request):
    """Прокси для эмбеддингов в LiteLLM."""
    import httpx

    body = await request.json()
    payload = {
        # agent-service только проксирует /v1/embeddings к LiteLLM (где живёт mistral-embed).
        # Эмбеддинги для базы знаний kb-service делает локально (deepvk/USER-bge-m3), см. kb-service.
        "model": body.get("model", "mistral-embed"),
        "input": body["input"],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.litellm_url}/v1/embeddings",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.litellm_master_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        return response.json()


@app.post("/v1/chat/completions")
async def openai_chat_completions(req: OpenAIRequest):
    """OpenAI-совместимый эндпоинт чата."""
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages is required")

    logger.info(f"openai chat: model={req.model}, messages={len(req.messages)}")

    # Build dialog_context from history (messages before the last user message)
    dialog_context = ""
    last_user_content = ""
    last_user_idx = -1
    for i, msg in enumerate(req.messages):
        if msg.role == "user":
            last_user_content = msg.content
            last_user_idx = i

    for i, msg in enumerate(req.messages):
        if i >= last_user_idx:
            break
        if msg.role == "system":
            continue
        prefix = "Пользователь: " if msg.role == "user" else "Вопрошалыч: "
        dialog_context += f"{prefix}{msg.content}\n"

    query = last_user_content
    if not query:
        raise HTTPException(status_code=400, detail="No user message found")

    state = AgentState(
        messages=[{"role": "user", "content": query}],
        dialog_context=dialog_context,
        request_id=str(uuid.uuid4()),
    )

    try:
        result = await graph.ainvoke(state)
        if isinstance(result, dict):
            answer = result.get("final_answer", "")
        else:
            answer = result.final_answer or ""

        resp_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        if req.stream:
            return _openai_stream_response(resp_id, req.model, answer)
        else:
            return {
                "id": resp_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": req.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": answer or "Не удалось обработать запрос.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": len(dialog_context) // 4,
                    "completion_tokens": len(answer) // 4,
                    "total_tokens": (len(dialog_context) + len(answer)) // 4,
                },
            }
    except Exception as e:
        logger.error(f"openai chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _openai_stream_response(resp_id: str, model: str, content: str):
    """Генерирует SSE-поток в формате OpenAI."""
    for i, char in enumerate(content):
        chunk = {
            "id": resp_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": char},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {chunk}\n\n"
    # Final chunk with finish_reason
    final = {
        "id": resp_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {final}\n\n"
    yield "data: [DONE]\n\n"


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "service": "agent-service", "version": "0.1.0"}


@app.get("/trace")
async def trace_get(request_id: str = Query(..., description="Request ID from X-Request-Id header")):
    """Получить трассировку выполнения агента по request_id."""
    traces = await get_traces(request_id)
    return {"request_id": request_id, "traces": traces}


@app.get("/mcp/tools")
async def list_available_tools():
    """Возвращает список инструментов, доступных агенту."""
    return {
        "servers": [
            {"name": "mcp-kb", "url": settings.mcp_kb_url, "tools": ["kb_search"]},
            {"name": "mcp-news", "url": settings.mcp_news_url, "tools": ["get_news", "get_events"]},
            {"name": "mcp-contacts", "url": settings.mcp_contacts_url, "tools": ["search_contacts"]},
            {"name": "mcp-library", "url": settings.mcp_library_url, "tools": ["get_library_info", "get_library_services", "get_library_guides"]},
            {"name": "mcp-sveden", "url": settings.mcp_sveden_url, "tools": ["get_sveden_info", "get_structure", "get_management"]},
            {"name": "mcp-fetch", "url": settings.mcp_fetch_url, "tools": ["fetch_url"]},
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=settings.agent_port)
