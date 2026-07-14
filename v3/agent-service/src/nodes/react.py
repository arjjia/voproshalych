"""ReAct-агент для multi-tool запросов.

Агент получает запрос, решает какие инструменты вызвать и в каком порядке,
агрегирует результаты и формирует финальный ответ.
"""

import json
import logging

from ..config import settings
from ..models import AgentState
from ..mcp_client import MCPClient
from ..trace_logger import write_trace

logger = logging.getLogger(__name__)

MCP_SERVERS = [
    ("kb", settings.mcp_kb_url, "kb_search", "Поиск по базе знаний ТюмГУ"),
    ("news", settings.mcp_news_url, "get_news", "Новости ТюмГУ"),
    ("events", settings.mcp_news_url, "get_events", "Мероприятия ТюмГУ"),
    ("fetch", settings.mcp_fetch_url, "fetch_url", "Загрузить содержимое веб-страницы по URL"),
]

TOOLS_DESCRIPTION = "\n".join(
    f"- {name}: {desc}" for name, _, _, desc in MCP_SERVERS
)

REACT_SYSTEM_PROMPT = """Ты — агент ассистента Тюменского государственного университета (ТюмГУ).
У тебя есть доступ к инструментам. Твоя задача — ответить на запрос пользователя,
используя нужные инструменты.

{dialog_context_block}

Доступные инструменты:
{TOOLS_DESCRIPTION}

Правила:
1. Подумай, какой инструмент(ы) нужны для ответа
2. Вызови инструмент(ы)
3. Проанализируй результат
4. Дай ответ пользователю

Формат ответа — JSON:
Если нужен вызов инструмента:
{{"action": "call_tool", "tool": "имя_инструмента", "args": {{...}}}}

Если готов ответить:
{{"action": "final_answer", "answer": "текст ответа", "sources": [{{"title": "...", "url": "..."}}]}}

Запрос пользователя: {query}

История вызовов:
{history}

Текущий шаг. Что делаешь?"""


async def react_node(state: AgentState) -> AgentState:
    """ReAct-агент: multi-tool запросы."""
    query = state.messages[-1]["content"] if state.messages else ""
    logger.info(f"react: query={query!r}")

    history: list[dict] = []
    max_iterations = 5

    for iteration in range(max_iterations):
        logger.info(f"react iteration {iteration + 1}/{max_iterations}")

        await write_trace(
            request_id=state.request_id, step=iteration + 1, phase="reasoning",
            thought=f"Iteration {iteration + 1}/{max_iterations}: анализирую запрос",
        )

        history_str = json.dumps(history, ensure_ascii=False, indent=2) if history else "Пока нет вызовов."
        dialog_context_block = f"История диалога:\n{state.dialog_context[:500]}\n\n" if state.dialog_context else ""
        prompt = REACT_SYSTEM_PROMPT.format(
            TOOLS_DESCRIPTION=TOOLS_DESCRIPTION,
            query=query,
            history=history_str,
            dialog_context_block=dialog_context_block,
        )

        decision = await _call_llm(prompt)

        try:
            decision = _extract_json(decision)
            data = json.loads(decision)
        except json.JSONDecodeError:
            logger.warning(f"react: invalid JSON, stopping: {decision[:200]}")
            state.final_answer = "Не удалось обработать запрос."
            return state

        action = data.get("action")

        if action == "final_answer":
            state.final_answer = data.get("answer", "Ответ сформирован.")
            state.sources = data.get("sources", [])
            logger.info(f"react: final answer: {state.final_answer[:100]}...")

            await write_trace(
                request_id=state.request_id, step=iteration + 1, phase="evaluation",
                thought="Финальный ответ сформирован",
                observation=f"Ответ: {state.final_answer[:200]}",
            )
            return state

        if action == "call_tool":
            tool_name = data.get("tool", "")
            tool_args = data.get("args", {})

            await write_trace(
                request_id=state.request_id, step=iteration + 1, phase="acting",
                action=f"call_{tool_name}",
                action_input=json.dumps(tool_args, ensure_ascii=False),
            )

            server_name = tool_name
            server_url = ""
            for name, url, _, _ in MCP_SERVERS:
                if name == tool_name:
                    server_url = url
                    break

            if not server_url:
                history.append({
                    "step": iteration + 1,
                    "tool": tool_name,
                    "error": f"Инструмент {tool_name} не найден",
                })
                await write_trace(
                    request_id=state.request_id, step=iteration + 1, phase="evaluation",
                    action="error",
                    observation=f"Инструмент {tool_name} не найден",
                )
                continue

            try:
                client = MCPClient(server_url)
                result = await client.call_tool(tool_name.split("_")[-1] if "_" in tool_name else tool_name, tool_args)
                result_text = _extract_text(result.get("content", "") if result else "")

                await write_trace(
                    request_id=state.request_id, step=iteration + 1, phase="evaluation",
                    observation=f"Результат: {result_text[:300]}",
                )

                history.append({
                    "step": iteration + 1,
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result_text[:500],
                })
            except Exception as e:
                logger.error(f"react: tool error {tool_name}: {e}")
                await write_trace(
                    request_id=state.request_id, step=iteration + 1, phase="evaluation",
                    action="error",
                    observation=f"Ошибка вызова {tool_name}: {e}",
                )
                history.append({
                    "step": iteration + 1,
                    "tool": tool_name,
                    "error": str(e),
                })

    state.final_answer = "Не удалось полностью обработать запрос за допустимое число шагов. Попробуйте переформулировать."
    return state


async def _call_llm(prompt: str) -> str:
    """Вызывает LLM для принятия решения."""
    import httpx

    payload = {
        "model": settings.model_priority[0],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
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


def _extract_json(text: str) -> str:
    """Извлекает JSON из текста (убирает markdown и мусор)."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


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
