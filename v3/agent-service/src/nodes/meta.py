"""Meta workflow — вопросы о самом ассистенте."""

import logging

from ..models import AgentState
from ..trace_logger import write_trace

logger = logging.getLogger(__name__)

META_RESPONSES = {
    "who_are_you": "Я — виртуальный ассистент Тюменского государственного университета (ТюмГУ). "
    "Я помогаю студентам, абитуриентам и сотрудникам находить информацию "
    "об университете: расписание, новости, контакты, документы, стипендии и многое другое. "
    "Задавайте любые вопросы!",
    "what_can_you_do": "Я умею:\n\n"
    "📚 **Искать информацию** в базе знаний ТюмГУ — документы, правила, стипендии\n"
    "📰 **Показывать новости** и мероприятия университета\n"
    "📞 **Находить контакты** подразделений и институтов\n"
    "🏛 **Рассказывать о библиотеке** — часы работы, сервисы, каталоги\n"
    "📋 **Предоставлять сведения** об организации (sveden.utmn.ru)\n\n"
    "Я постоянно развиваюсь! В будущем появятся расписание, оценки и другие возможности.",
    "help": "**Помощь по ассистенту ТюмГУ**\n\n"
    "Вы можете спросить меня о:\n"
    "• Университете, факультетах, правилах\n"
    "• Стипендиях, общежитии, документах\n"
    "• Новостях и мероприятиях\n"
    "• Контактах подразделений\n"
    "• Библиотеке и её сервисах\n\n"
    "Просто задайте вопрос естественным языком!",
}


async def meta_node(state: AgentState) -> AgentState:
    """Обрабатывает meta-запросы."""
    query = state.messages[-1]["content"].lower().strip() if state.messages else ""

    logger.info(f"meta: query={query!r}")

    await write_trace(
        request_id=state.request_id, step=1, phase="reasoning",
        thought=f"Meta-запрос: {query[:200]}",
    )

    if any(w in query for w in ["кто ты", "что ты", "ты кто", "расскажи о себе"]):
        state.final_answer = META_RESPONSES["who_are_you"]
    elif any(w in query for w in ["что ты умеешь", "что можешь", "функции", "возможности"]):
        state.final_answer = META_RESPONSES["what_can_you_do"]
    else:
        state.final_answer = META_RESPONSES["help"]

    state.sources = []
    return state
