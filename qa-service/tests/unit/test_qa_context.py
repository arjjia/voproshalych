"""Тесты обработки пользовательского контекста в QA route."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import qa.api.routes.qa as qa_route
from qa.config.prompts import NO_DOCUMENT_DATA_RESPONSE
from qa.llm.providers.base import LLMResponse
from qa.models.request import QARequest, QAResponse


def test_build_lightrag_question_includes_dialog_context() -> None:
    """История диалога должна добавляться к запросу для LightRAG."""
    question = qa_route._build_lightrag_question(
        question="А что с ним?",
        dialog_context="Пользователь: Речь об общежитии",
    )

    assert "История текущего диалога:" in question
    assert "Пользователь: Речь об общежитии" in question
    assert "Последний вопрос пользователя: А что с ним?" in question


@pytest.mark.asyncio
async def test_query_classic_rag_includes_dialog_context_in_prompt() -> None:
    """Classic RAG должен учитывать и KB-контекст, и историю диалога."""
    mock_response = LLMResponse(
        content="Тестовый ответ",
        model="open-mistral-nemo",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    mock_pool = MagicMock()
    mock_pool.select_model.return_value = "mistral"
    mock_pool.call = AsyncMock(return_value=mock_response)

    chunks = [
        {
            "text": "Подача документов идет до 25 июля.",
            "title": "Сроки приема",
            "source_url": "https://example.org/admission",
        }
    ]

    with patch("qa.api.routes.qa.get_llm_pool", return_value=mock_pool), patch(
        "qa.api.routes.qa.get_embedding",
        return_value=[0.1, 0.2, 0.3],
    ), patch(
        "qa.api.routes.qa.search_chunks",
        new=AsyncMock(return_value=chunks),
    ):
        response = await qa_route._query_classic_rag(
            question="А до какого числа?",
            dialog_context="Пользователь: Мы обсуждаем поступление",
        )

    assert response.answer == "Тестовый ответ"
    prompt = mock_pool.call.call_args.kwargs["prompt"]
    assert "История текущего диалога:" in prompt
    assert "Пользователь: Мы обсуждаем поступление" in prompt
    assert "Контекст из документов ТюмГУ:" in prompt
    assert "Подача документов идет до 25 июля." in prompt
    assert "https://example.org/admission" in prompt
    assert "Подробнее:" in prompt
    assert "При ответе на вопрос ИСПОЛЬЗУЙ ТОЛЬКО информацию из предоставленного контекста." in prompt
    assert "Не называй себя ChatGPT, Claude или другой моделью." in prompt


@pytest.mark.asyncio
async def test_query_classic_rag_returns_no_documents_response_without_llm() -> None:
    """Если retrieval не нашел релевантных чанков, LLM вызываться не должен."""
    mock_pool = MagicMock()
    mock_pool.select_model.return_value = "mistral"
    mock_pool.call = AsyncMock()

    with patch("qa.api.routes.qa.get_llm_pool", return_value=mock_pool), patch(
        "qa.api.routes.qa.get_embedding",
        return_value=[0.1, 0.2, 0.3],
    ), patch(
        "qa.api.routes.qa.search_chunks",
        new=AsyncMock(return_value=[]),
    ):
        response = await qa_route._query_classic_rag(
            question="Несуществующий документ ТюмГУ",
            dialog_context="Пользователь: Мы обсуждаем учебный вопрос",
        )

    assert response.answer == NO_DOCUMENT_DATA_RESPONSE
    assert response.model == "kb-search"
    mock_pool.select_model.assert_not_called()
    mock_pool.call.assert_not_called()


@pytest.mark.asyncio
async def test_ask_question_passes_context_to_classic_rag_fallback() -> None:
    """Контекст не должен теряться при fallback с LightRAG на classic RAG."""
    expected_response = QAResponse(
        answer="Fallback answer",
        model="open-mistral-nemo",
        sources=[],
    )

    async def _passthrough_wait_for(coro, timeout):
        return await coro

    with patch(
        "qa.api.routes.qa._query_lightrag",
        new=AsyncMock(side_effect=RuntimeError("LightRAG unavailable")),
    ), patch(
        "qa.api.routes.qa._query_classic_rag",
        new=AsyncMock(return_value=expected_response),
    ) as mock_classic, patch(
        "qa.api.routes.qa.asyncio.wait_for",
        new=AsyncMock(side_effect=_passthrough_wait_for),
    ):
        response = await qa_route.ask_question(
            QARequest(
                question="А что с ним?",
                context="Пользователь: Мы говорим про общежитие",
            )
        )

    assert response == expected_response
    mock_classic.assert_awaited_once_with(
        "А что с ним?",
        dialog_context="Пользователь: Мы говорим про общежитие",
    )
