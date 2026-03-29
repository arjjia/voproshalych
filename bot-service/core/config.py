"""Объекты конфигурации для core-сервиса."""

from dataclasses import dataclass
import os


def _parse_bool(value: str, default: bool = False) -> bool:
    """Преобразует строку окружения в булево значение."""

    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    """Настройки запуска FastAPI core-сервиса."""

    app_name: str = os.getenv("BOT_CORE_APP_NAME", "bot-core")
    app_version: str = os.getenv("BOT_CORE_APP_VERSION", "0.1.0")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "voproshalych")
    postgres_user: str = os.getenv("POSTGRES_USER", "voproshalych")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "voproshalych")
    qa_service_url: str = os.getenv("QA_SERVICE_URL", "http://qa-service:8004")
    qa_service_timeout_seconds: float = float(
        os.getenv("QA_SERVICE_TIMEOUT_SECONDS", "300")
    )
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    vk_bot_token: str = os.getenv("VK_BOT_TOKEN", "")
    max_bot_token: str = os.getenv("MAX_BOT_TOKEN", "")
    max_bot_internal_url: str = os.getenv(
        "MAX_BOT_INTERNAL_URL",
        "http://max-bot:8081",
    )
    dialog_context_limit_messages: int = int(
        os.getenv("DIALOG_CONTEXT_LIMIT_MESSAGES", "7")
    )
    holiday_newsletter_enabled: bool = _parse_bool(
        os.getenv("HOLIDAY_NEWSLETTER_ENABLED", "true"),
        default=True,
    )
    holiday_newsletter_run_hour: int = int(
        os.getenv("HOLIDAY_NEWSLETTER_RUN_HOUR", "9")
    )
    holiday_newsletter_run_minute: int = int(
        os.getenv("HOLIDAY_NEWSLETTER_RUN_MINUTE", "0")
    )


settings = Settings()
