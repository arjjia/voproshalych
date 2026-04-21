"""Unit тесты для question_router."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from qa.services.question_router import (
    QUESTION_TYPE_KB,
    QUESTION_TYPE_SYSTEM,
    QUESTION_TYPE_GENERAL,
    QuestionClassification,
    classify_and_expand,
    _parse_classification_response,
)


class TestParseClassificationResponse:
    """Тесты для _parse_classification_response."""

    def test_valid_json_type_1(self):
        raw = '{"type": 1, "expanded_query": "как оплатить обучение"}'
        result = _parse_classification_response(raw, "как оплатить")
        assert result.question_type == QUESTION_TYPE_KB
        assert result.expanded_query == "как оплатить обучение"

    def test_valid_json_type_2(self):
        raw = '{"type": 2, "expanded_query": "кто создал бота"}'
        result = _parse_classification_response(raw, "кто тебя создал")
        assert result.question_type == QUESTION_TYPE_SYSTEM
        assert result.expanded_query == "кто создал бота"

    def test_valid_json_type_3(self):
        raw = '{"type": 3, "expanded_query": "приветствие"}'
        result = _parse_classification_response(raw, "привет")
        assert result.question_type == QUESTION_TYPE_GENERAL
        assert result.expanded_query == "приветствие"

    def test_invalid_type_defaults_to_kb(self):
        raw = '{"type": 99, "expanded_query": "запрос"}'
        result = _parse_classification_response(raw, "вопрос")
        assert result.question_type == QUESTION_TYPE_KB

    def test_non_int_type_defaults_to_kb(self):
        raw = '{"type": "kb", "expanded_query": "запрос"}'
        result = _parse_classification_response(raw, "вопрос")
        assert result.question_type == QUESTION_TYPE_KB

    def test_missing_type_defaults_to_kb(self):
        raw = '{"expanded_query": "запрос"}'
        result = _parse_classification_response(raw, "вопрос")
        assert result.question_type == QUESTION_TYPE_KB

    def test_empty_expanded_uses_original(self):
        raw = '{"type": 1, "expanded_query": ""}'
        result = _parse_classification_response(raw, "оригинальный вопрос")
        assert result.expanded_query == "оригинальный вопрос"

    def test_missing_expanded_uses_original(self):
        raw = '{"type": 1}'
        result = _parse_classification_response(raw, "оригинальный вопрос")
        assert result.expanded_query == "оригинальный вопрос"

    def test_no_json_falls_back(self):
        raw = "Это просто текст без JSON"
        result = _parse_classification_response(raw, "вопрос")
        assert result.question_type == QUESTION_TYPE_KB
        assert result.expanded_query == "вопрос"

    def test_json_in_markdown_code_block(self):
        raw = '```json\n{"type": 2, "expanded_query": "о боте"}\n```'
        result = _parse_classification_response(raw, "о боте")
        assert result.question_type == QUESTION_TYPE_SYSTEM
        assert result.expanded_query == "о боте"

    def test_truncates_long_expanded_query(self):
        long_query = "а" * 2000
        raw = json.dumps({"type": 1, "expanded_query": long_query})
        result = _parse_classification_response(raw, "вопрос")
        assert len(result.expanded_query) == 1500

    def test_confidence_parsed(self):
        raw = '{"type": 1, "expanded_query": "запрос", "confidence": 0.9}'
        result = _parse_classification_response(raw, "вопрос")
        assert result.confidence == 0.9

    def test_default_confidence(self):
        raw = '{"type": 1, "expanded_query": "запрос"}'
        result = _parse_classification_response(raw, "вопрос")
        assert result.confidence == 0.5


class TestClassifyAndExpand:
    """Тесты для classify_and_expand (async с моками)."""

    @pytest.mark.asyncio
    async def test_success_kb_type(self):
        mock_response = MagicMock()
        mock_response.content = '{"type": 1, "expanded_query": "расписание занятий"}'

        with patch("qa.services.question_router.get_llm_pool") as mock_pool, \
             patch("qa.services.question_router.get_llm_config") as mock_config:
            mock_pool_instance = MagicMock()
            mock_pool_instance.select_model.return_value = "mistral"
            mock_pool_instance.call = AsyncMock(return_value=mock_response)
            mock_pool.return_value = mock_pool_instance
            mock_config.return_value = MagicMock(
                query_expansion_timeout=20.0,
            )

            result = await classify_and_expand("когда пары", request_id="test-1")
            assert result.question_type == QUESTION_TYPE_KB
            assert result.expanded_query == "расписание занятий"

    @pytest.mark.asyncio
    async def test_no_provider_fallback(self):
        with patch("qa.services.question_router.get_llm_pool") as mock_pool, \
             patch("qa.services.question_router.get_llm_config") as mock_config:
            mock_pool_instance = MagicMock()
            mock_pool_instance.select_model.return_value = None
            mock_pool.return_value = mock_pool_instance
            mock_config.return_value = MagicMock(
                query_expansion_timeout=20.0,
            )

            result = await classify_and_expand("вопрос")
            assert result.question_type == QUESTION_TYPE_KB
            assert result.expanded_query == "вопрос"

    @pytest.mark.asyncio
    async def test_timeout_fallback(self):
        import asyncio

        with patch("qa.services.question_router.get_llm_pool") as mock_pool, \
             patch("qa.services.question_router.get_llm_config") as mock_config:
            mock_pool_instance = MagicMock()
            mock_pool_instance.select_model.return_value = "mistral"
            mock_pool_instance.call = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_pool.return_value = mock_pool_instance
            mock_config.return_value = MagicMock(
                query_expansion_timeout=0.01,
            )

            result = await classify_and_expand("вопрос")
            assert result.question_type == QUESTION_TYPE_KB
            assert result.expanded_query == "вопрос"

    @pytest.mark.asyncio
    async def test_exception_fallback(self):
        with patch("qa.services.question_router.get_llm_pool") as mock_pool, \
             patch("qa.services.question_router.get_llm_config") as mock_config:
            mock_pool_instance = MagicMock()
            mock_pool_instance.select_model.return_value = "mistral"
            mock_pool_instance.call = AsyncMock(side_effect=RuntimeError("fail"))
            mock_pool.return_value = mock_pool_instance
            mock_config.return_value = MagicMock(
                query_expansion_timeout=20.0,
            )

            result = await classify_and_expand("вопрос")
            assert result.question_type == QUESTION_TYPE_KB
            assert result.expanded_query == "вопрос"
