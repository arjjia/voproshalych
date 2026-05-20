"""Конфигурация Базы Знаний."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


def _find_env_file() -> Path | None:
    """Найти .env файл в директории проекта.

    Поиск выполняется от текущего файла вверх по директориям.

    Returns:
        Путь к .env файлу или None, если не найден
    """
    current = Path(__file__).parent
    for _ in range(5):
        env_path = current / ".env"
        if env_path.exists():
            return env_path
        current = current.parent
    return None


if env_file := _find_env_file():
    load_dotenv(env_file)


class KBConfig(BaseSettings):
    """Конфигурация Базы Знаний.

    Attributes:
        embedding_model: Название модели для эмбеддингов
        chunk_size: Максимальный размер чанка в символах
        chunk_overlap: Перекрытие между чанками в символах
        min_chunk_size: Минимальный размер чанка для сохранения
    """

    embedding_model: str = "deepvk/USER-bge-m3"
    chunk_size: int = 500
    chunk_overlap: int = 50
    min_chunk_size: int = 50

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


class RerankerConfig(BaseSettings):
    """Конфигурация реранкера (cross-encoder).

    Attributes:
        reranker_enabled: Включить second-stage reranking
        reranker_model: Название модели реранкера
        retrieval_candidates: Количество чанков из LightRAG до реранкинга
        reranker_top_k: Количество чанков после реранкинга
        reranker_max_length: Максимальная длина токенов для пары query+passage
    """

    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    retrieval_candidates: int = 30
    reranker_top_k: int = 10
    reranker_max_length: int = 512

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


_kb_config: KBConfig | None = None
_reranker_config: RerankerConfig | None = None


def get_kb_config() -> KBConfig:
    """Получить конфигурацию Базы Знаний.

    Returns:
        Объект KBConfig с настройками
    """
    global _kb_config
    if _kb_config is None:
        _kb_config = KBConfig()
    return _kb_config


def get_reranker_config() -> RerankerConfig:
    """Получить конфигурацию реранкера.

    Returns:
        Объект RerankerConfig с настройками
    """
    global _reranker_config
    if _reranker_config is None:
        _reranker_config = RerankerConfig()
    return _reranker_config
