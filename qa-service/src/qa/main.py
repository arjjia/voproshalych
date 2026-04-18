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
        # LightRAG читает POSTGRES_DATABASE, а compose передаёт POSTGRES_DB —
        # проксируем имя, чтобы не дублировать переменные окружения.
        if "POSTGRES_DATABASE" not in os.environ and "POSTGRES_DB" in os.environ:
            os.environ["POSTGRES_DATABASE"] = os.environ["POSTGRES_DB"]

        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc
        from .lightrag_adapter import (
            llm_model_func,
            _embedding_func,
            create_lightrag_config,
        )

        config = create_lightrag_config()

        logger.info(f"Initializing LightRAG with config: {config}")

        embedding_dimension = config.get("embedding_dimension", 1024)
        model_name = config.get("model_name", "default")

        storage_type = config.get("storage_type", "PostgreSQL")

        # Determine graph storage based on available extensions
        # PGGraphStorage requires Apache AGE extension (dawsonlp/postgres-batteries-inc)
        # NetworkXStorage is fallback when AGE is not available
        use_pg_graph = config.get("use_pg_graph", True)
        chunk_token_size = config.get("chunk_token_size", 1024)
        chunk_overlap_token_size = config.get("chunk_overlap_token_size", 200)
        tokenizer = config.get("tokenizer")

        _lightrag = LightRAG(
            working_dir=config["working_dir"],
            llm_model_func=llm_model_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=embedding_dimension,
                max_token_size=512,
                func=_embedding_func,
                model_name=model_name,
            ),
            graph_storage="PGGraphStorage" if use_pg_graph else "NetworkXStorage",
            vector_storage="PGVectorStorage" if storage_type == "PostgreSQL" else None,
            kv_storage="PGKVStorage" if storage_type == "PostgreSQL" else None,
            doc_status_storage="PGDocStatusStorage" if storage_type == "PostgreSQL" else None,
            chunk_token_size=chunk_token_size,
            chunk_overlap_token_size=chunk_overlap_token_size,
            tokenizer=tokenizer,
            llm_model_max_async=1,
            embedding_func_max_async=1,
        )

        if storage_type == "PostgreSQL":
            await _lightrag.initialize_storages()

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
