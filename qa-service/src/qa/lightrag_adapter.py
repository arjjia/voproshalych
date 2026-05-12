"""Адаптеры для интеграции LightRAG с существующим LLM Pool и embedding моделью."""

import asyncio
import json
import logging
import math
import os
import re
from typing import Any, List

import numpy as np

from qa.llm import get_llm_pool, get_llm_config
from qa.kb.embedding import get_embeddings_batch

logger = logging.getLogger(__name__)

_last_extracted_keywords: dict = {"high_level": [], "low_level": []}


def get_last_extracted_keywords() -> dict:
    """Получить ключевые слова, извлечённые при последнем вызове LightRAG."""
    return _last_extracted_keywords.copy()


def override_lightrag_prompts():
    from lightrag.prompt import PROMPTS

    PROMPTS["entity_extraction_examples"] = [
        """<Entity_types>
["Organization","Department","Person","Position","Document","Service","System","Event","Rule","Resource"]

<Input Text>
```
Тюменский государственный университет (ТюмГУ) расположен в городе Тюмень. Университет включает Институт математики и компьютерных наук (ИМиКН), Институт биологии и Колледж информационных технологий. Ректор университета — Иванов Пётр Сергеевич. Студенты могут получить справку об обучении через Единый личный кабинет на сайте elk.utmn.ru.
```

<Output>
entity{tuple_delimiter}Тюменский государственный университет{tuple_delimiter}Organization{tuple_delimiter}Тюменский государственный университет (ТюмГУ) — высшее учебное заведение в городе Тюмень.
entity{tuple_delimiter}Институт математики и компьютерных наук{tuple_delimiter}Department{tuple_delimiter}ИМиКН — структурное подразделение ТюмГУ.
entity{tuple_delimiter}Иванов Пётр Сергеевич{tuple_delimiter}Person{tuple_delimiter}Ректор Тюменского государственного университета.
entity{tuple_delimiter}Единый личный кабинет{tuple_delimiter}System{tuple_delimiter}Информационная система ТюмГУ на сайте elk.utmn.ru.
entity{tuple_delimiter}Справка об обучении{tuple_delimiter}Document{tuple_delimiter}Документ, получаемый через Единый личный кабинет.
relation{tuple_delimiter}Тюменский государственный университет{tuple_delimiter}Институт математики и компьютерных наук{tuple_delimiter}structure{tuple_delimiter}ИМиКН является подразделением ТюмГУ.
relation{tuple_delimiter}Тюменский государственный университет{tuple_delimiter}Иванов Пётр Сергеевич{tuple_delimiter}leadership{tuple_delimiter}Иванов П.С. — ректор ТюмГУ.
relation{tuple_delimiter}Единый личный кабинет{tuple_delimiter}Справка об обучении{tuple_delimiter}service{tuple_delimiter}Через ЕЛК можно получить справку.
{completion_delimiter}

""",
        """<Entity_types>
["Organization","Department","Person","Position","Document","Service","System","Event","Rule","Resource"]

<Input Text>
```
Для подключения к Wi-Fi университета используйте корпоративную учётную запись. Сертификат можно получить в кабинете 205 корпуса 1. Правила использования сети описаны в Положении об информационных системах от 15.03.2024.
```

<Output>
entity{tuple_delimiter}Wi-Fi университета{tuple_delimiter}Resource{tuple_delimiter}Беспроводная сеть ТюмГУ.
entity{tuple_delimiter}Корпоративная учётная запись{tuple_delimiter}System{tuple_delimiter}Учётная запись для авторизации в системах университета.
entity{tuple_delimiter}Положение об информационных системах{tuple_delimiter}Document{tuple_delimiter}Документ от 15.03.2024 с правилами использования сети.
relation{tuple_delimiter}Wi-Fi университета{tuple_delimiter}Корпоративная учётная запись{tuple_delimiter}access{tuple_delimiter}Для Wi-Fi нужна корпоративная учётная запись.
{completion_delimiter}

""",
    ]


_tokenizer = None

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[А-ЯЁA-Z])" r"|(?<=;)\s*\n(?=\s*—)" r"|(?<=:)\s*\n(?=\s*—)"
)


class HuggingFaceTokenizer:
    """Токенизатор на основе HuggingFace для LightRAG.

    Использует токенизатор embedding модели, чтобы количество
    токенов совпадало.
    """

    def __init__(
        self,
        model_name: str = "deepvk/USER-bge-m3",
    ):
        from transformers import AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model_name = model_name
        logger.info(f"HuggingFaceTokenizer initialized with {model_name}")

    def encode(self, content: str) -> List[int]:
        return self._tokenizer.encode(content, add_special_tokens=True)

    def decode(self, tokens: List[int]) -> str:
        return self._tokenizer.decode(tokens, skip_special_tokens=True)


def get_lightrag_tokenizer() -> HuggingFaceTokenizer:
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = HuggingFaceTokenizer(
            "deepvk/USER-bge-m3"
        )
    return _tokenizer


def sentence_aware_chunking(
    tokenizer,
    content: str,
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    chunk_overlap_token_size: int = 50,
    chunk_token_size: int = 500,
) -> list[dict[str, Any]]:
    """Чанкинг с сохранением целостности предложений.

    Разбивает текст на предложения, группирует в чанки до chunk_token_size
    токенов. Границы чанков всегда совпадают с границами предложений.
    Overlap реализуется целыми предложениями из конца предыдущего чанка.

    Args:
        tokenizer: Токенизатор с методом encode()
        content: Текст для разбиения
        split_by_character: Не используется (совместимость с LightRAG)
        split_by_character_only: Не используется
        chunk_overlap_token_size: Целевое количество токенов перекрытия
        chunk_token_size: Максимальное количество токенов на чанк

    Returns:
        Список словарей с ключами tokens, content, chunk_order_index
    """
    if not content or not content.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", content)
    sentences = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        parts = _SENTENCE_SPLIT_RE.split(para)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)

    if not sentences:
        return []

    chunks: list[dict[str, Any]] = []
    current_sentences: list[str] = []
    current_tokens = 0
    overlap_sentences: list[str] = []
    overlap_tokens = 0

    for sent in sentences:
        sent_tokens = len(tokenizer.encode(sent))

        if sent_tokens > chunk_token_size * 1.5:
            sub_lines = [s.strip() for s in sent.split("\n") if s.strip()]
            if len(sub_lines) > 1:
                for line in sub_lines:
                    line_tokens = len(tokenizer.encode(line))
                    if (
                        current_tokens + line_tokens > chunk_token_size
                        and current_sentences
                    ):
                        chunk_text = " ".join(current_sentences)
                        chunks.append(
                            {
                                "tokens": current_tokens,
                                "content": chunk_text.strip(),
                                "chunk_order_index": len(chunks),
                            }
                        )
                        current_sentences = []
                        current_tokens = 0
                    current_sentences.append(line)
                    current_tokens += line_tokens
                continue

        if current_tokens + sent_tokens > chunk_token_size and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(
                {
                    "tokens": current_tokens,
                    "content": chunk_text.strip(),
                    "chunk_order_index": len(chunks),
                }
            )

            overlap_sentences = []
            overlap_tokens = 0
            for s in reversed(current_sentences):
                s_tok = len(tokenizer.encode(s))
                if (
                    overlap_tokens + s_tok <= chunk_overlap_token_size
                    or not overlap_sentences
                ):
                    overlap_sentences.insert(0, s)
                    overlap_tokens += s_tok
                else:
                    break

            current_sentences = list(overlap_sentences)
            current_tokens = overlap_tokens

        current_sentences.append(sent)
        current_tokens += sent_tokens

    if current_sentences:
        chunk_text = " ".join(current_sentences)
        chunks.append(
            {
                "tokens": current_tokens,
                "content": chunk_text.strip(),
                "chunk_order_index": len(chunks),
            }
        )

    return chunks


_llm_call_count = 0
_llm_last_call_time = 0.0
LLM_CALL_DELAY = 0.5


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
    иначе использует основной LLM Pool (mistral → openrouter).
    Добавляет задержку между вызовами для избежания rate limiting.

    Таймауты по кейсам:
    - keyword_extraction: keyword_extraction_timeout (по умолчанию 30s)
    - graph_building: graph_building_timeout (по умолчанию 180s)
    - default: answer_generation_timeout (по умолчанию 90s)
    """
    global _llm_call_count, _llm_last_call_time

    if keyword_extraction:
        use_case = "keyword_extraction"
    elif len(prompt) > 3000:
        use_case = "graph_building"
    else:
        use_case = "default"
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
        if llm_model == "ollama":
            from qa.llm.providers.ollama import OllamaProvider

            provider = OllamaProvider()
            logger.info(f"Using LightRAG model: Ollama/{provider._model}")
            response = await provider.generate(
                prompt=full_prompt,
                temperature=config.default_temperature,
                max_tokens=config.default_max_tokens,
            )
            if response.content:
                _log_keywords_if_extraction(keyword_extraction, response.content)
                return response.content
            raise ValueError("Ollama returned empty content")

        elif llm_model == "mistral":
            from qa.llm.providers.mistral import MistralProvider

            provider = MistralProvider()
            logger.info(f"Using LightRAG model: Mistral (timeout={timeout}s)")
            response = await asyncio.wait_for(
                provider.generate(
                    prompt=full_prompt,
                    temperature=config.default_temperature,
                    max_tokens=config.default_max_tokens,
                ),
                timeout=timeout,
            )
            if response.content:
                _log_keywords_if_extraction(keyword_extraction, response.content)
                return response.content
            raise ValueError("Mistral returned empty content")

        else:
            from qa.llm.providers.openrouter import OpenRouterProvider

            provider = OpenRouterProvider(
                models=config.openrouter_models,
                fallback_model="openrouter/free",
            )
            logger.info(
                f"Using LightRAG model: {llm_model or 'OpenRouter'} (timeout={timeout}s)"
            )
            response = await asyncio.wait_for(
                provider.generate(
                    prompt=full_prompt,
                    temperature=config.default_temperature,
                    max_tokens=config.default_max_tokens,
                ),
                timeout=timeout,
            )
            if response.content:
                _log_keywords_if_extraction(keyword_extraction, response.content)
                return response.content
            raise ValueError("OpenRouter returned empty content")

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


def _log_keywords_if_extraction(keyword_extraction: bool, content: str) -> None:
    """Если это вызов keyword_extraction — распарсить и залогировать ключевые слова."""
    global _last_extracted_keywords
    if not keyword_extraction:
        return
    try:
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            hl = parsed.get("high_level_keywords", [])
            ll = parsed.get("low_level_keywords", [])
            _last_extracted_keywords = {"high_level": hl, "low_level": ll}
            logger.info(
                f"[PIPELINE] Keywords extracted: " f"high_level={hl}, low_level={ll}"
            )
        else:
            logger.warning(f"[PIPELINE] Keyword extraction: no JSON found in response")
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[PIPELINE] Keyword extraction parse failed: {e}")


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
        "model_name": os.getenv(
            "LIGHT_RAG_MODEL_NAME",
            "deepvk-user-bge-m3",
        ),
        "use_pg_graph": os.getenv("LIGHT_RAG_USE_PG_GRAPH", "true").lower() == "true",
        "chunk_token_size": int(os.getenv("CHUNK_TOKEN_SIZE", "500")),
        "chunk_overlap_token_size": int(os.getenv("CHUNK_OVERLAP_TOKEN_SIZE", "50")),
        "tokenizer": get_lightrag_tokenizer(),
    }


async def create_lightrag_instance():
    """Создать и инициализировать экземпляр LightRAG.

    Не зависит от FastAPI. Может использоваться из скриптов
    (fill_kb_unified, benchmarks) без запуска веб-сервера.

    Returns:
        Готовый к работе экземпляр LightRAG
    """
    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc

    override_lightrag_prompts()
    config = create_lightrag_config()

    embedding_dimension = config.get("embedding_dimension", 1024)
    model_name = config.get("model_name", "default")
    storage_type = config.get("storage_type", "PostgreSQL")
    use_pg_graph = config.get("use_pg_graph", True)
    chunk_token_size = config.get("chunk_token_size", 500)
    chunk_overlap_token_size = config.get("chunk_overlap_token_size", 50)
    tokenizer = config.get("tokenizer")

    rag = LightRAG(
        working_dir=config["working_dir"],
        llm_model_func=llm_model_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=embedding_dimension,
            max_token_size=512,
            func=_embedding_func,
            model_name=model_name,
        ),
        graph_storage=("PGGraphStorage" if use_pg_graph else "NetworkXStorage"),
        vector_storage=("PGVectorStorage" if storage_type == "PostgreSQL" else None),
        kv_storage=("PGKVStorage" if storage_type == "PostgreSQL" else None),
        doc_status_storage=(
            "PGDocStatusStorage" if storage_type == "PostgreSQL" else None
        ),
        chunk_token_size=chunk_token_size,
        chunk_overlap_token_size=chunk_overlap_token_size,
        chunking_func=sentence_aware_chunking,
        tokenizer=tokenizer,
        llm_model_max_async=1,
        embedding_func_max_async=1,
        default_llm_timeout=3600,
        addon_params={"language": "Russian"},
    )

    if storage_type == "PostgreSQL":
        await rag.initialize_storages()

    _patch_merge_chunks()

    logger.info("LightRAG instance created and initialized")
    return rag


_CHUNK_MERGE_PATCHED = False

_CFG_A_VECTOR_WEIGHT = 1.2
_CFG_A_ENTITY_WEIGHT = 0.8
_CFG_A_RELATION_WEIGHT = 0.6
_CFG_A_GRAPH_ONLY_PENALTY = 0.9
_CFG_A_VECTOR_CONFIRM_BOOST = 1.15
_CFG_A_FREQ_GAMMA = 0.35
_CFG_A_FREQ_CAP = 3.0


def _patch_merge_chunks():
    """Заменить round-robin слияние LightRAG на score-based cfgA.

    Веса cfgA (по результатам бенчмарков):
    - vector: 1.2, entity: 0.8, relation: 0.6
    - graph_only_penalty: 0.9, vector_confirm_boost: 1.15
    - freq_gamma: 0.35, freq_cap: 3.0
    """
    global _CHUNK_MERGE_PATCHED
    if _CHUNK_MERGE_PATCHED:
        return

    import lightrag.operate as operate_mod

    _find_entities = operate_mod._find_related_text_unit_from_entities
    _find_relations = operate_mod._find_related_text_unit_from_relations

    def _cid(chunk: dict) -> str | None:
        return chunk.get("chunk_id") or chunk.get("id")

    def _res(chunk: dict, cid: str) -> dict:
        return {
            "content": chunk["content"],
            "file_path": chunk.get("file_path", "unknown_source"),
            "chunk_id": cid,
        }

    async def _cfg_a_merge(
        filtered_entities,
        filtered_relations,
        vector_chunks,
        query="",
        knowledge_graph_inst=None,
        text_chunks_db=None,
        query_param=None,
        chunks_vdb=None,
        chunk_tracking=None,
        query_embedding=None,
    ):
        if chunk_tracking is None:
            chunk_tracking = {}

        entity_chunks = []
        if filtered_entities and text_chunks_db:
            entity_chunks = await _find_entities(
                filtered_entities,
                query_param,
                text_chunks_db,
                knowledge_graph_inst,
                query,
                chunks_vdb,
                chunk_tracking=chunk_tracking,
                query_embedding=query_embedding,
            )

        relation_chunks = []
        if filtered_relations and text_chunks_db:
            relation_chunks = await _find_relations(
                filtered_relations,
                query_param,
                text_chunks_db,
                entity_chunks,
                query,
                chunks_vdb,
                chunk_tracking=chunk_tracking,
                query_embedding=query_embedding,
            )

        def _freq_bonus(chunk_id: str) -> float:
            freq = int(
                chunk_tracking.get(chunk_id, {}).get("frequency", 1) or 1
            )
            return min(
                _CFG_A_FREQ_CAP,
                1.0 + _CFG_A_FREQ_GAMMA * math.log1p(max(freq - 1, 0)),
            )

        def _rr_pos(position: int, offset: int) -> float:
            return 1.0 / (3 * position + offset)

        scored: dict[str, dict] = {}

        for pos, chunk in enumerate(vector_chunks):
            c = _cid(chunk)
            if not c:
                continue
            score = _CFG_A_VECTOR_WEIGHT * _rr_pos(pos, 1)
            prev = scored.get(c)
            if prev is None or prev["_score"] < score:
                scored[c] = {
                    "content": chunk["content"],
                    "file_path": chunk.get("file_path", "unknown_source"),
                    "chunk_id": c,
                    "_score": score,
                    "_from_vector": True,
                }

        for pos, chunk in enumerate(entity_chunks):
            c = _cid(chunk)
            if not c:
                continue
            score = _CFG_A_ENTITY_WEIGHT * _rr_pos(pos, 2) * _freq_bonus(c)
            prev = scored.get(c)
            if prev is None:
                scored[c] = {
                    "content": chunk["content"],
                    "file_path": chunk.get("file_path", "unknown_source"),
                    "chunk_id": c,
                    "_score": score * _CFG_A_GRAPH_ONLY_PENALTY,
                    "_from_vector": False,
                }
            else:
                boost = (
                    _CFG_A_VECTOR_CONFIRM_BOOST
                    if prev.get("_from_vector")
                    else 1.0
                )
                prev["_score"] += score * boost

        for pos, chunk in enumerate(relation_chunks):
            c = _cid(chunk)
            if not c:
                continue
            score = _CFG_A_RELATION_WEIGHT * _rr_pos(pos, 3) * _freq_bonus(c)
            prev = scored.get(c)
            if prev is None:
                scored[c] = {
                    "content": chunk["content"],
                    "file_path": chunk.get("file_path", "unknown_source"),
                    "chunk_id": c,
                    "_score": score * _CFG_A_GRAPH_ONLY_PENALTY,
                    "_from_vector": False,
                }
            else:
                boost = (
                    _CFG_A_VECTOR_CONFIRM_BOOST
                    if prev.get("_from_vector")
                    else 1.0
                )
                prev["_score"] += score * boost

        merged = sorted(scored.values(), key=lambda x: -x["_score"])
        origin_len = (
            len(vector_chunks)
            + len(entity_chunks)
            + len(relation_chunks)
        )
        for item in merged:
            item.pop("_score", None)
            item.pop("_from_vector", None)

        logger.info(
            "Score merge cfgA: %d+%d+%d -> %d (dedup %d)",
            len(vector_chunks),
            len(entity_chunks),
            len(relation_chunks),
            len(merged),
            origin_len - len(merged),
        )
        return merged

    operate_mod._merge_all_chunks = _cfg_a_merge
    _CHUNK_MERGE_PATCHED = True
    logger.info("LightRAG _merge_all_chunks patched: score merge cfgA")


def _extract_file_paths_from_search_data(
    search_data: dict,
    top_k: int = 10,
) -> list[str]:
    """Извлечь file_path из результата aquery_data LightRAG.

    Значения file_path извлекаются из chunks и references
    в порядке ранжирования с дедупликацией.

    Args:
        search_data: Результат rag.aquery_data()
        top_k: Максимум значений для возврата

    Returns:
        Список file_path в порядке ранжирования
    """
    if search_data.get("status") != "success":
        return []

    result_data = search_data.get("data", {})
    chunks = result_data.get("chunks", [])
    references = result_data.get("references", [])

    file_paths: list[str] = []
    seen: set[str] = set()

    for chunk in chunks:
        fp = chunk.get("file_path", "")
        if fp and fp not in seen:
            file_paths.append(fp)
            seen.add(fp)
            if len(file_paths) >= top_k:
                return file_paths

    for ref in references:
        fp = ref.get("file_path", "")
        if fp and fp not in seen:
            file_paths.append(fp)
            seen.add(fp)
            if len(file_paths) >= top_k:
                return file_paths

    return file_paths


def extract_urls_from_search_data(
    search_data: dict,
    top_k: int = 10,
) -> list[str]:
    """Извлечь URL источников из результата aquery_data LightRAG."""
    file_paths = _extract_file_paths_from_search_data(search_data, top_k * 3)
    urls: list[str] = []
    for fp in file_paths:
        if fp.startswith("http"):
            urls.append(fp)
            if len(urls) >= top_k:
                break
    return urls


def extract_chunk_ids_from_search_data(
    search_data: dict,
    top_k: int = 10,
) -> list[str]:
    """Извлечь chunk_id из результата aquery_data LightRAG.

    Каждый chunk в ответе содержит поле ``chunk_id`` — используется
    именно оно, а не file_path.

    Args:
        search_data: Результат rag.aquery_data()
        top_k: Максимум chunk_id для возврата

    Returns:
        Список chunk_id в порядке ранжирования
    """
    if search_data.get("status") != "success":
        return []

    result_data = search_data.get("data", {})
    chunks = result_data.get("chunks", [])

    chunk_ids: list[str] = []
    seen: set[str] = set()

    for chunk in chunks:
        cid = chunk.get("chunk_id", "")
        if cid and cid not in seen:
            chunk_ids.append(cid)
            seen.add(cid)
            if len(chunk_ids) >= top_k:
                break

    return chunk_ids
