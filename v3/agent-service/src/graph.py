"""LangGraph граф агента.

Граф: start → supervisor → (kb_workflow | meta | react | clarify) → end
"""

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from .models import AgentState, Intent
from .nodes.supervisor import supervisor_node
from .nodes.kb_workflow import kb_workflow_node
from .nodes.meta import meta_node
from .nodes.react import react_node
from .trace_logger import write_trace

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Строит граф агента."""
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("kb_workflow", kb_workflow_node)
    workflow.add_node("meta", meta_node)
    workflow.add_node("react", react_node)
    workflow.add_node("clarify", _clarify_node)
    workflow.add_node("off_topic", _off_topic_node)

    workflow.set_entry_point("supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        router,
        {
            "kb_workflow": "kb_workflow",
            "meta": "meta",
            "react": "react",
            "clarify": "clarify",
            "off_topic": "off_topic",
            "end": END,
        },
    )

    workflow.add_edge("kb_workflow", END)
    workflow.add_edge("meta", END)
    workflow.add_edge("react", END)
    workflow.add_edge("clarify", END)
    workflow.add_edge("off_topic", END)

    return workflow.compile()


def router(state: AgentState) -> Literal["kb_workflow", "meta", "react", "clarify", "off_topic", "end"]:
    """Определяет, какой узел запустить следующим."""
    intent = state.intent

    if intent == Intent.KB_QA:
        return "kb_workflow"
    elif intent == Intent.META:
        return "meta"
    elif intent == Intent.TOOL_REQUIRED:
        return "react"
    elif intent == Intent.CLARIFY:
        return "clarify"
    elif intent == Intent.OFF_TOPIC:
        return "off_topic"
    else:
        return "end"


async def _clarify_node(state: AgentState) -> AgentState:
    """Узел уточнения запроса."""
    query = state.messages[-1]["content"] if state.messages else ""
    state.final_answer = (
        f"Не совсем понял ваш запрос: «{query[:100]}». "
        f"Пожалуйста, уточните, что именно вас интересует в ТюмГУ? "
        f"Например: стипендии, расписание, контакты, новости."
    )
    state.sources = []
    return state


async def _off_topic_node(state: AgentState) -> AgentState:
    """Узел для off-topic запросов."""
    state.final_answer = (
        "Я — ассистент Тюменского государственного университета (ТюмГУ) "
        "и могу отвечать только на вопросы, связанные с университетом. "
        "Пожалуйста, задайте вопрос про учёбу, поступление, стипендии, "
        "контакты или другие аспекты жизни ТюмГУ."
    )
    state.sources = []
    return state
