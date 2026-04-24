"""Основное приложение FastAPI для QA-сервиса.

Содержит endpoints для вопросов-ответов и проверки здоровья сервиса.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from .api import qa_router, health_router, holiday_router, kb_router
from .kb.embedding import get_embedding_model
from .llm import get_llm_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

_lightrag: Optional["LightRAG"] = None
_lightrag_ready: bool = False


def get_lightrag():
    """Получить экземпляр LightRAG."""
    global _lightrag
    return _lightrag


def is_lightrag_ready() -> bool:
    """Проверить, инициализирован ли LightRAG."""
    global _lightrag_ready
    return _lightrag_ready


async def init_lightrag():
    """Инициализировать LightRAG с PGGraphStorage и PGVectorStorage."""
    global _lightrag, _lightrag_ready

    try:
        from .lightrag_adapter import create_lightrag_instance

        _lightrag = await create_lightrag_instance()
        _lightrag_ready = True
        logger.info("LightRAG initialized successfully with PostgreSQL storage")

    except Exception as e:
        logger.error(f"Failed to initialize LightRAG: {e}")
        _lightrag = None
        _lightrag_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения.

    При старте инициализирует LLM Pool, embedding модель и LightRAG.
    При завершении логирует остановку сервиса.

    Args:
        app: Приложение FastAPI
    """
    logger.info("Starting QA service...")

    logger.info("Preloading embedding model...")
    get_embedding_model()
    logger.info("Embedding model preloaded")

    llm_pool = get_llm_pool()
    available = llm_pool.get_available_providers()
    logger.info(f"Available LLM providers: {available}")

    # LightRAG всегда включен (гибридный поиск: вектора + граф)
    await init_lightrag()

    yield

    logger.info("Shutting down QA service...")


def create_app() -> FastAPI:
    """Создать и настроить приложение FastAPI."""
    app = FastAPI(
        title="QA Service",
        description="QA Service with LightRAG (hybrid vector + graph search)",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(qa_router)
    app.include_router(holiday_router)
    app.include_router(kb_router)

    return app


app = create_app()
