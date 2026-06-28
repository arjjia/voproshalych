"""Unit тесты для payload_builder."""

import pytest

from qa.services.payload_builder import (
    build_messages,
)


class TestBuildMessages:
    """Тесты для build_messages."""

    def test_basic_messages(self):
        messages = build_messages(
            system_prompt="Ты помощник.",
            question="Как дела?",
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Ты помощник."
        assert messages[1]["role"] == "user"
        assert "Как дела?" in messages[1]["content"]

    def test_with_search_context(self):
        messages = build_messages(
            system_prompt="Ты помощник.",
            question="Что такое сессия?",
            search_context="Сессия — это экзаменационный период.",
        )
        user_content = messages[1]["content"]
        assert "Сессия — это экзаменационный период." in user_content
        assert "Что такое сессия?" in user_content

    def test_with_dialog_context(self):
        messages = build_messages(
            system_prompt="Ты помощник.",
            question="А когда она начинается?",
            dialog_context="Студент спрашивал про сессию.",
            dialog_context_prompt="История:",
        )
        user_content = messages[1]["content"]
        assert "Студент спрашивал про сессию." in user_content
        assert "А когда она начинается?" in user_content

    def test_all_parts_present(self):
        messages = build_messages(
            system_prompt="Ты помощник.",
            question="Вопрос",
            search_context="Контекст поиска",
            dialog_context="История",
            dialog_context_prompt="Прошлое:",
        )
        user_content = messages[1]["content"]
        assert "Прошлое:" in user_content
        assert "История" in user_content
        assert "Контекст поиска" in user_content
        assert "Вопрос" in user_content

    def test_empty_contexts_ignored(self):
        messages = build_messages(
            system_prompt="Ты помощник.",
            question="Вопрос",
            search_context="",
            dialog_context="",
        )
        user_content = messages[1]["content"]
        assert "Контекст из базы знаний" not in user_content
        assert "История диалога" not in user_content

    def test_system_prompt_always_preserved(self):
        messages = build_messages(
            system_prompt="Ты Вопрошалыч.",
            question="Вопрос",
            search_context="x" * 30000,
        )
        assert messages[0]["content"] == "Ты Вопрошалыч."

    def test_question_always_present(self):
        messages = build_messages(
            system_prompt="Ты помощник.",
            question="Мой уникальный вопрос",
            search_context="x" * 30000,
            dialog_context="y" * 10000,
        )
        assert "Мой уникальный вопрос" in messages[1]["content"]
