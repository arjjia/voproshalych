"""Тесты BotService для передачи истории диалога в QA service."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from services.bot_service import BotService
from services.qa_service_client import QAServiceRateLimited


def test_handle_dialog_message_passes_history_via_context() -> None:
    """История диалога должна передаваться отдельным полем context."""
    service = BotService()
    service._dialog_service = MagicMock()
    service._dialog_service.get_or_create_active_session.return_value = SimpleNamespace(
        id=42
    )
    service._dialog_service.build_context.return_value = "Пользователь: Речь о поступлении"
    service._ask_qa_service = MagicMock(
        return_value={"answer": "Ответ", "expanded_query": None, "keywords": None, "model": ""}
    )

    reply = service._handle_dialog_message(
        question="А что со сроками?",
        user=SimpleNamespace(id=7),
    )

    assert reply == "Ответ"
    service._ask_qa_service.assert_called_once_with(
        question="А что со сроками?",
        context="Пользователь: Речь о поступлении",
    )
    service._dialog_service.save_question_answer.assert_called_once_with(
        session_id=42,
        question="А что со сроками?",
        answer="Ответ",
        expanded_query=None,
        keywords=None,
        model_used="",
    )


def test_handle_dialog_message_skips_empty_history_context() -> None:
    """Пустую историю не нужно отправлять как непустой контекст."""
    service = BotService()
    service._dialog_service = MagicMock()
    service._dialog_service.get_or_create_active_session.return_value = SimpleNamespace(
        id=11
    )
    service._dialog_service.build_context.return_value = ""
    service._ask_qa_service = MagicMock(
        return_value={"answer": "Ответ", "expanded_query": None, "keywords": None, "model": ""}
    )

    service._handle_dialog_message(
        question="Когда прием документов?",
        user=SimpleNamespace(id=5),
    )

    service._ask_qa_service.assert_called_once_with(
        question="Когда прием документов?",
        context=None,
    )


def test_ask_qa_service_returns_overload_message_on_rate_limit() -> None:
    """Rate limit QA-сервиса должен давать понятный пользовательский ответ."""
    service = BotService()
    service._qa_service_client = MagicMock()
    service._qa_service_client.ask.side_effect = QAServiceRateLimited(
        "QA service rate limited"
    )

    result = service._ask_qa_service("Когда начинается семестр?")

    assert result["answer"] == (
        "Сервис сейчас перегружен запросами. "
        "Попробуйте повторить вопрос чуть позже."
    )
