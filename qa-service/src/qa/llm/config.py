"""Конфигурация LLM пула."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from dotenv import load_dotenv


def _find_env_file() -> Path | None:
    """Найти .env файл."""
    current = Path(__file__).parent
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return None


if env_file := _find_env_file():
    load_dotenv(env_file)


class LLMConfig(BaseSettings):
    """Конфигурация LLM провайдеров.

    Attributes:
        mistral_api_key: API ключ Mistral AI
        mistral_model: Модель Mistral по умолчанию
        openrouter_api_key: API ключ OpenRouter
        openrouter_models: Список моделей OpenRouter по приоритету качества
        openrouter_fallback_model: Резервная модель OpenRouter (random free)
        gigachat_client_id: Client ID GigaChat
        gigachat_client_secret: Client Secret GigaChat
        model_priority: Приоритет провайдеров (по умолчанию: openrouter, gigachat, mistral)
        lightrag_llm_model: Модель для индексации LightRAG (по умолчанию: первая из openrouter_models)
        default_temperature: Температура по умолчанию
        default_max_tokens: Максимальное количество токенов

        Таймауты по моделям (секунды):
        nemotron_timeout: Таймаут для Nemotron 3 Super (1M context)
        qwen_timeout: Таймаут для Qwen 3.6 Plus (1M context + CoT)
        mistral_timeout: Таймаут для Mistral Nemo
        gigachat_timeout: Таймаут для GigaChat

        Таймауты по кейсам (секунды):
        keyword_extraction_timeout: Извлечение ключевых слов
        query_expansion_timeout: Предобработка вопроса пользователя
        answer_generation_timeout: Генерация ответа
        graph_building_timeout: Построение графа знаний
    """

    mistral_api_key: str = Field(default="", validation_alias="MISTRAL_API_KEY")
    mistral_model: str = Field(default="open-mistral-nemo", validation_alias="MISTRAL_MODEL")
    openrouter_api_key: str = Field(default="")
    openrouter_models: list[str] = Field(
        default=[
            "nvidia/nemotron-3-super-120b-a12b:free",
            "qwen/qwen3.6-plus:free",
        ]
    )
    openrouter_fallback_model: str = Field(default="openrouter/free")
    gigachat_client_id: str = Field(default="")
    gigachat_client_secret: str = Field(default="")

    model_priority: list[str] = Field(default=["openrouter", "gigachat", "mistral"])
    lightrag_llm_model: str = Field(default="")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen3.6:35b")

    default_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=2048, ge=1)

    nemotron_timeout: int = Field(default=120)
    qwen_timeout: int = Field(default=180)
    mistral_timeout: int = Field(default=600)
    gigachat_timeout: int = Field(default=120)

    keyword_extraction_timeout: int = Field(default=30)
    query_expansion_timeout: int = Field(default=20)
    answer_generation_timeout: int = Field(default=120)
    graph_building_timeout: int = Field(default=600)

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


def get_llm_config() -> LLMConfig:
    """Получить конфигурацию LLM."""
    return LLMConfig()
