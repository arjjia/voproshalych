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
    chunk_size: int = 1024
    chunk_overlap: int = 0
    min_chunk_size: int = 50

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


_config: KBConfig | None = None


def get_kb_config() -> KBConfig:
    """Получить конфигурацию Базы Знаний.

    Returns:
        Объект KBConfig с настройками
    """
    global _config
    if _config is None:
        _config = KBConfig()
    return _config
