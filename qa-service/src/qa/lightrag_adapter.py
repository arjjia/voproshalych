"""Адаптеры для интеграции LightRAG с существующим LLM Pool и embedding моделью."""

import asyncio
import logging
import os
from typing import Any, List

import numpy as np

from qa.llm import get_llm_pool, get_llm_config
from qa.kb.embedding import get_embeddings_batch

logger = logging.getLogger(__name__)

_tokenizer = None


class HuggingFaceTokenizer:
    """Токенизатор на основе HuggingFace для LightRAG.

    Использует тот же токенизатор что и embedding модель (deepvk/USER-bge-m3),
    чтобы количество токенов совпадало.
    """

    def __init__(self, model_name: str = "deepvk/USER-bge-m3"):
        """Инициализировать токенизатор.

        Args:
            model_name: Название модели HuggingFace
        """
        from transformers import AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model_name = model_name
        logger.info(f"HuggingFaceTokenizer initialized with {model_name}")

    def encode(self, content: str) -> List[int]:
        """Закодировать текст в токены.

        Args:
            content: Текст для токенизации

        Returns:
            Список токенов
        """
        return self._tokenizer.encode(content, add_special_tokens=True)

    def decode(self, tokens: List[int]) -> str:
        """Декодировать токены в текст.

        Args:
            tokens: Список токенов

        Returns:
            Текст
        """
        return self._tokenizer.decode(tokens, skip_special_tokens=True)


def get_lightrag_tokenizer() -> HuggingFaceTokenizer:
    """Получить токенизатор для LightRAG.

    Использует SentencePiece токенизатор от deepvk/USER-bge-m3.

    Returns:
        Экземпляр HuggingFaceTokenizer
    """
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = HuggingFaceTokenizer("deepvk/USER-bge-m3")
    return _tokenizer


_llm_call_count = 0
_llm_last_call_time = 0.0
LLM_CALL_DELAY = 5.0


def _get_lightrag_llm_model() -> str:
    """Получить модель для LightRAG из конфига или env переменной."""
    config = get_llm_config()
    return config.lightrag_llm_model or os.getenv("LIGHT_RAG_LLM_MODEL", "")


def _get_timeout_for_use_case(use_case: str) -> float:
    """Получить таймаут для конкретного кейса использования.

    Args:
        use_case: Кейс использования (keyword_extraction, graph_building, default)

    Returns:
        Таймаут в секундах
    """
    config = get_llm_config()

    use_case_lower = use_case.lower()
    if "keyword" in use_case_lower:
        return float(config.keyword_extraction_timeout)
    elif "graph" in use_case_lower or "build" in use_case_lower:
        return float(config.graph_building_timeout)
    else:
        return float(config.answer_generation_timeout)


async def llm_model_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list | None = None,
    keyword_extraction: bool = False,
    **kwargs: Any,
) -> str:
    """Кастомная LLM функция для LightRAG.

    Использует модель из LIGHT_RAG_LLM_MODEL если указана,
    иначе использует основной LLM Pool (openrouter → gigachat → mistral).
    Добавляет задержку между вызовами для избежания rate limiting.

    Таймауты по кейсам:
    - keyword_extraction: keyword_extraction_timeout (по умолчанию 30s)
    - graph_building: graph_building_timeout (по умолчанию 180s)
    - default: answer_generation_timeout (по умолчанию 90s)
    """
    global _llm_call_count, _llm_last_call_time

    use_case = "keyword_extraction" if keyword_extraction else "default"
    timeout = _get_timeout_for_use_case(use_case)

    current_time = asyncio.get_event_loop().time()
    time_since_last_call = current_time - _llm_last_call_time

    if _llm_call_count > 0 and time_since_last_call < LLM_CALL_DELAY:
        wait_time = LLM_CALL_DELAY - time_since_last_call
        logger.info(f"Rate limit protection: waiting {wait_time:.1f}s before LLM call")
        await asyncio.sleep(wait_time)

    _llm_call_count += 1
    _llm_last_call_time = asyncio.get_event_loop().time()

    llm_model = _get_lightrag_llm_model()
    llm_pool = get_llm_pool()
    config = get_llm_config()

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    try:
        if llm_model == "mistral":
            from qa.llm.providers.mistral import MistralProvider

            provider = MistralProvider()
            if provider.is_available():
                logger.info(
                    f"Using LightRAG model: Mistral (timeout={timeout}s)"
                )
                try:
                    response = await asyncio.wait_for(
                        provider.generate(
                            prompt=full_prompt,
                            temperature=config.default_temperature,
                            max_tokens=config.default_max_tokens,
                        ),
                        timeout=timeout,
                    )
                    if response.content:
                        return response.content
                except asyncio.TimeoutError:
                    logger.warning(f"Mistral timeout after {timeout}s")
                    raise
                except Exception as e:
                    if "429" in str(e):
                        logger.warning("Mistral rate limited, trying OpenRouter fallback")
                    else:
                        logger.warning(f"Mistral failed: {e}")
        else:
            from qa.llm.providers.openrouter import OpenRouterProvider

            provider = OpenRouterProvider(
                models=config.openrouter_models,
                fallback_model="openrouter/free",
            )
            if provider.is_available():
                logger.info(
                    f"Using LightRAG model: {llm_model or 'OpenRouter fallback'} (timeout={timeout}s)"
                )
                try:
                    response = await asyncio.wait_for(
                        provider.generate(
                            prompt=full_prompt,
                            temperature=config.default_temperature,
                            max_tokens=config.default_max_tokens,
                        ),
                        timeout=timeout,
                    )
                    if response.content:
                        return response.content
                except asyncio.TimeoutError:
                    logger.warning(f"OpenRouter timeout after {timeout}s")
                    raise
                except Exception as e:
                    if "429" in str(e):
                        logger.warning(f"OpenRouter rate limited: {e}")

        logger.info("Falling back to LLM pool")
        response = await asyncio.wait_for(
            llm_pool.call(prompt=full_prompt),
            timeout=timeout,
        )
        if response.content:
            return response.content
        raise ValueError("LLM returned empty content")
    except asyncio.TimeoutError:
        logger.error(f"LLM call timeout after {timeout}s for use_case={use_case}")
        if keyword_extraction:
            return "[]"
        raise
    except Exception as e:
        logger.error(f"LLM call failed in LightRAG: {e}")
        if keyword_extraction:
            return "[]"
        raise


async def _embedding_func(texts: list[str]) -> np.ndarray:
    """Async функция эмбеддингов для LightRAG.

    Args:
        texts: Список текстов для эмбеддингов

    Returns:
        NumPy массив эмбеддингов
    """
    embeddings = get_embeddings_batch(texts)
    return np.array(embeddings)


def create_lightrag_config() -> dict:
    """Создать конфигурацию для LightRAG."""
    config = get_llm_config()
    return {
        "working_dir": os.getenv("LIGHT_RAG_WORKING_DIR", "/app/lightrag_data"),
        "storage_type": os.getenv("LIGHT_RAG_STORAGE_TYPE", "PostgreSQL"),
        "postgres_uri": os.getenv(
            "LIGHT_RAG_POSTGRES_URI",
            "postgresql://voproshalych:voproshalych@postgres:5432/voproshalych",
        ),
        "embedding_dimension": 1024,
        "model_name": os.getenv("LIGHT_RAG_MODEL_NAME", "deepvk-user-bge-m3"),
        "use_pg_graph": os.getenv("LIGHT_RAG_USE_PG_GRAPH", "true").lower() == "true",
        "chunk_token_size": int(os.getenv("CHUNK_TOKEN_SIZE", "1024")),
        "chunk_overlap_token_size": int(os.getenv("CHUNK_OVERLAP_TOKEN_SIZE", "200")),
        "tokenizer": get_lightrag_tokenizer(),
    }
