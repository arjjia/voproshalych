"""Supervisor-классификатор.

Определяет интент запроса (KB, Meta, Tool, Off-topic, Clarify)
и сложность (simple, multi-step).
"""

import json
import logging

from ..config import settings
from ..models import AgentState, Complexity, Intent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — классификатор запросов в ассистенте Тюменского государственного университета (ТюмГУ).
Определи тип запроса пользователя и его сложность.

{dialog_context_block}

Типы запросов:
- kb_qa: Вопрос про университет — правила, стипендии, факультеты, общежитие, документы, контакты, расписания, учебные программы, история, общая информация. Вопрос требует поиска в базе знаний.
- meta: Вопрос про самого ассистента: "кто ты?", "что ты умеешь?", "help", "start", "что ты можешь?".
- tool_required: Запрос, требующий вызова инструментов: "какие новости?", "контакты деканата", "информация о библиотеке", "сведения об организации".
- off_topic: Вопрос не про университет и не про ассистента.
- clarify: Вопрос неясен, нужно уточнение.

Сложность:
- simple: Один чёткий вопрос, один источник ответа.
- multi_step: Вопрос требует несколько шагов или несколько источников.

Ответь строго в формате JSON:
{{"intent": "kb_qa|meta|tool_required|off_topic|clarify", "complexity": "simple|multi_step"}}

Пользовательский запрос: {query}"""


async def supervisor_node(state: AgentState) -> AgentState:
    """Определяет интент и сложность запроса."""
    query = state.messages[-1]["content"] if state.messages else ""
    logger.info(f"supervisor: query={query!r}")

    dialog_context_block = f"История диалога:\n{state.dialog_context[:500]}\n\n" if state.dialog_context else ""

    try:
        prompt = SYSTEM_PROMPT.format(
            query=query[:500],
            dialog_context_block=dialog_context_block,
        )
        result = await _call_classifier(prompt)
        data = json.loads(result)

        intent_str = data.get("intent", "kb_qa")
        complexity_str = data.get("complexity", "simple")

        state.intent = Intent(intent_str)
        state.complexity = Complexity(complexity_str)

        logger.info(f"supervisor: intent={state.intent.value}, complexity={state.complexity.value}")

    except Exception as e:
        logger.error(f"supervisor error: {e}")
        state.intent = Intent.KB_QA
        state.complexity = Complexity.SIMPLE

    return state


async def _call_classifier(prompt: str) -> str:
    """Вызывает LLM для классификации."""
    import httpx

    payload = {
        "model": settings.classifier_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
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
