"""KB workflow — поиск по базе знаний через mcp-kb."""

import json
import logging

from ..config import settings
from ..models import AgentState
from ..mcp_client import MCPClient
from ..trace_logger import write_trace

logger = logging.getLogger(__name__)

KB_SYSTEM_PROMPT = """Ты — ассистент Тюменского государственного университета (ТюмГУ).
Отвечай на вопросы студентов, абитуриентов и сотрудников университета.

{context}

{dialog_context_block}

Вопрос: {query}

Дай развёрнутый ответ на русском языке. Всегда указывай источники, если они есть."""


async def kb_workflow_node(state: AgentState) -> AgentState:
    """Workflow для вопросов по базе знаний."""
    query = state.messages[-1]["content"] if state.messages else ""
    logger.info(f"kb_workflow: query={query!r}")

    await write_trace(
        request_id=state.request_id, step=1, phase="acting",
        action="kb_search",
        action_input=json.dumps({"query": query[:200]}, ensure_ascii=False),
    )

    try:
        mcp = MCPClient(settings.mcp_kb_url)
        kb_result = await mcp.call_tool("kb_search", {"query": query, "workspace": "public"})

        if kb_result and kb_result.get("content"):
            kb_answer = _extract_text(kb_result["content"])
        else:
            kb_answer = "Не удалось найти информацию."

        await write_trace(
            request_id=state.request_id, step=1, phase="evaluation",
            observation=f"KB ответ получен, длина={len(kb_answer)}",
        )

        llm_answer = await _generate_final_answer(query, kb_answer, state.dialog_context)
        state.final_answer = llm_answer
        state.sources = [{"title": "База знаний ТюмГУ", "url": ""}]

    except Exception as e:
        logger.error(f"kb_workflow error: {e}")
        state.final_answer = f"Произошла ошибка при поиске: {e}"
        state.error = str(e)

        await write_trace(
            request_id=state.request_id, step=1, phase="evaluation",
            action="error",
            observation=f"Ошибка KB workflow: {e}",
        )

    return state


async def _generate_final_answer(query: str, kb_context: str, dialog_context: str = "") -> str:
    """Генерирует финальный ответ LLM на основе контекста."""
    import httpx

    dialog_context_block = f"История диалога:\n{dialog_context[:500]}\n\n" if dialog_context else ""
    prompt = KB_SYSTEM_PROMPT.format(
        context=f"Контекст из базы знаний:\n{kb_context[:3000]}",
        dialog_context_block=dialog_context_block,
        query=query,
    )

    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.7,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.litellm_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.litellm_master_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _extract_text(content: list | str) -> str:
    """Извлекает текст из MCP-ответа."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)
    return str(content)
