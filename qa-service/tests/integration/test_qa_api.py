"""Интеграционные тесты для QA API.

Тестируют основные endpoints QA сервиса:
- Health check endpoint
- QA endpoint с мокированными LLM провайдерами
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from qa.main import app
from qa.llm.providers.base import LLMResponse


@pytest.fixture
def client():
    """Фикстура для тестового клиента.

    Созда TestClient для FastAPI приложения.

    Returns:
        TestClient для выполнения HTTP запросов
    """
    return TestClient(app)


def _mock_classification(question_type=3, expanded_query="расширенный запрос"):
    """Создать мок классификации вопроса."""
    from qa.services.question_router import QuestionClassification
    return QuestionClassification(
        question_type=question_type,
        expanded_query=expanded_query,
        confidence=0.9,
    )


class TestHealthEndpoint:
    """Тесты для health check endpoint.

    Проверяет доступность сервиса и корректность ответов.
    """

    def test_health_check(self, client):
        """Тест health check.

        Проверяет что сервис возвращает статус 200
        и корректную структуру ответа.

        Args:
            client: TestClient для выполнения запросов
        """
        with patch("qa.api.routes.health.get_llm_pool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.get_available_providers.return_value = ["mistral"]
            mock_pool.return_value = mock_pool_instance

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "version" in data

    def test_health_check_no_providers(self, client):
        """Тест health check без доступных провайдеров.

        Проверяет что корректно обрабатывается ситуация
        когда нет доступных LLM провайдеров.

        Args:
            client: TestClient для выполнения запросов
        """
        with patch("qa.api.routes.health.get_llm_pool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.get_available_providers.return_value = []
            mock_pool.return_value = mock_pool_instance

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"

    def test_readiness_check_ready(self, client):
        """Тест readiness check.

        Проверяет readiness endpoint возвращает корректный статус
        когда есть доступные LLM провайдеры.

        Args:
            client: TestClient для выполнения запросов
        """
        with patch("qa.api.routes.health.get_llm_pool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.get_available_providers.return_value = ["mistral"]
            mock_pool.return_value = mock_pool_instance

            response = client.get("/health/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"

    def test_readiness_check_not_ready(self, client):
        """Тест readiness check без провайдеров.

        Проверяет readiness endpoint корректно обрабатывает
        ситуацию когда нет доступных LLM провайдеров.

        Args:
            client: TestClient для выполнения запросов
        """
        with patch("qa.api.routes.health.get_llm_pool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.get_available_providers.return_value = []
            mock_pool.return_value = mock_pool_instance

            response = client.get("/health/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "no_providers"


class TestQAEndpoint:
    """Тесты для QA endpoint.

    Тестируют обработку вопросов пользователей и ответы от LLM
    с мокированными провайдерами.
    """

    def test_ask_question_success(self, client):
        """Тест успешного запроса.

        Проверяет корректность ответа на вопрос
        и что LLM вызывается с правильными параметрами.

        Args:
            client: TestClient для выполнения запросов
        """
        mock_response = LLMResponse(
            content="Это тестовый ответ от LLM",
            model="open-mistral-nemo",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with patch("qa.main.is_lightrag_ready", return_value=True), \
             patch("qa.services.question_router.classify_and_expand",
                   new_callable=AsyncMock,
                   return_value=_mock_classification(question_type=3)), \
             patch("qa.api.routes.qa.get_llm_pool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.call = AsyncMock(return_value=mock_response)
            mock_pool.return_value = mock_pool_instance

            response = client.post("/qa", json={"question": "Привет, как дела?"})

            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert data["model"] == "open-mistral-nemo"
            assert data["question_type"] == 3

    def test_ask_question_with_context(self, client):
        """Тест запроса с контекстом.

        Проверяет что контекст корректно передаётся
        и LLM получает messages с system и user ролями.

        Args:
            client: TestClient для выполнения запросов
        """
        mock_response = LLMResponse(
            content="Ответ на основе контекста",
            model="open-mistral-nemo",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        )

        with patch("qa.main.is_lightrag_ready", return_value=True), \
             patch("qa.services.question_router.classify_and_expand",
                   new_callable=AsyncMock,
                   return_value=_mock_classification(question_type=3)), \
             patch("qa.api.routes.qa.get_llm_pool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool_instance.call = AsyncMock(return_value=mock_response)
            mock_pool.return_value = mock_pool_instance

            response = client.post(
                "/qa",
                json={
                    "question": "Что ты знаешь об этом?",
                    "context": "Это про ТюмГУ",
                },
            )

            assert response.status_code == 200
            call_kwargs = mock_pool_instance.call.call_args.kwargs
            assert "messages" in call_kwargs
            messages = call_kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"

    def test_ask_question_lightrag_not_ready(self, client):
        """Тест запроса когда LightRAG не готов.

        Проверяет что корректно возвращается ошибка 503.

        Args:
            client: TestClient для выполнения запросов
        """
        with patch("qa.main.is_lightrag_ready", return_value=False):
            response = client.post("/qa", json={"question": "Привет"})

            assert response.status_code == 503
            assert "LightRAG not initialized" in response.json()["detail"]

    def test_ask_question_empty_question(self, client):
        """Тест запроса с пустым вопросом.

        Проверяет валидацию запроса на пустой вопрос.

        Args:
            client: TestClient для выполнения запросов
        """
        response = client.post("/qa", json={})

        assert response.status_code == 422

    def test_ask_question_kb_type_with_search(self, client):
        """Тест KB-вопроса с поиском LightRAG.

        Проверяет что pipeline вызывает aquery_data для KB вопросов.

        Args:
            client: TestClient для выполнения запросов
        """
        mock_llm_response = LLMResponse(
            content="Расписание занятий доступно в личном кабинете.",
            model="open-mistral-nemo",
            usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        )

        mock_search_data = {
            "status": "success",
            "data": {
                "chunks": [{"content": "Расписание на sem.utmn.ru", "file_path": "https://utmn.ru/schedule"}],
                "entities": [],
                "relationships": [],
            },
            "metadata": {"keywords": {"high_level": ["расписание"], "low_level": []}},
            "references": [],
        }

        with patch("qa.main.is_lightrag_ready", return_value=True), \
             patch("qa.services.question_router.classify_and_expand",
                   new_callable=AsyncMock,
                   return_value=_mock_classification(question_type=1, expanded_query="расписание занятий")), \
             patch("qa.api.routes.qa.get_llm_pool") as mock_pool, \
             patch("qa.main.get_lightrag") as mock_lightrag:
            mock_pool_instance = MagicMock()
            mock_pool_instance.call = AsyncMock(return_value=mock_llm_response)
            mock_pool.return_value = mock_pool_instance

            mock_rag = MagicMock()
            mock_rag.aquery_data = AsyncMock(return_value=mock_search_data)
            mock_lightrag.return_value = mock_rag

            response = client.post("/qa", json={"question": "когда пары?"})

            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert data["question_type"] == 1
            assert len(data["sources"]) > 0
