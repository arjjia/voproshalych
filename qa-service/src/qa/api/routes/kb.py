"""API роуты для работы с Базой Знаний."""

import json
import logging
import uuid

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import create_engine, text

from qa.kb.chunking import Chunk, TextChunker
from qa.kb.config import get_kb_config
from qa.kb.embedding import get_embedding
from qa.kb.parsers.web import WebPageParser


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["kb"])

_parser = WebPageParser()
_chunker = TextChunker(
    chunk_size=get_kb_config().chunk_size,
    chunk_overlap=get_kb_config().chunk_overlap,
    min_chunk_size=get_kb_config().min_chunk_size,
)

_engine = None


def get_engine():
    """Получить движок базы данных."""
    global _engine
    if _engine is None:
        db_url = "postgresql://voproshalych:voproshalych@postgres:5432/voproshalych"
        _engine = create_engine(db_url)
    return _engine


class DocumentRequest(BaseModel):
    """Запрос на скачивание документа."""

    url: HttpUrl


class ChunkResponse(BaseModel):
    """Ответ с данными чанка."""

    id: str
    text: str
    source_url: str
    title: str
    chunk_index: int


class DocumentResponse(BaseModel):
    """Ответ со скачанным документом."""

    url: str
    title: str
    chunks_count: int


class ImportToLightRAGRequest(BaseModel):
    """Запрос на импорт в LightRAG."""

    chunk_ids: Optional[list[str]] = None
    limit: Optional[int] = None
    version_id: Optional[str] = None
    notes: str = ""


async def _save_chunk_to_db(chunk: Chunk, embedding: list[float]) -> None:
    """Сохранить чанк и эмбеддинг в базу данных."""
    engine = get_engine()
    chunk_id = uuid.uuid4()

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO chunks (id, text, source_url, source_type, title)
                VALUES (:id, :text, :source_url, :source_type, :title)
            """),
            {
                "id": str(chunk_id),
                "text": chunk.text,
                "source_url": chunk.source_url,
                "source_type": "web",
                "title": chunk.title,
            },
        )
        conn.commit()

        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        conn.execute(
            text("""
                INSERT INTO embeddings (chunk_id, embedding, embedding_vector)
                VALUES (:chunk_id, :embedding, :embedding_vector::vector)
            """),
            {
                "chunk_id": str(chunk_id),
                "embedding": json.dumps(embedding),
                "embedding_vector": embedding_str,
            },
        )
        conn.commit()


@router.post("/documents", response_model=DocumentResponse)
async def download_document(request: DocumentRequest) -> DocumentResponse:
    """Скачать и распарсить веб-страницу или PDF, затем чанкировать и создать эмбеддинги.

    Args:
        request: DocumentRequest с URL документа для скачивания

    Returns:
        DocumentResponse с информацией о распарсенном документе
    """
    try:
        parsed = await _parser.parse(str(request.url))
        logger.info(f"Распарсен документ: {parsed.title}")

        chunks_count = 0
        for chunk in _chunker.chunk_text(
            text=parsed.text_content,
            source_url=parsed.url,
            title=parsed.title,
        ):
            embedding = get_embedding(chunk.text)
            await _save_chunk_to_db(chunk, embedding)
            chunks_count += 1
            logger.info(f"Создан чанк {chunks_count}: {chunk.text[:50]}...")

        return DocumentResponse(
            url=parsed.url,
            title=parsed.title,
            chunks_count=chunks_count,
        )

    except Exception as e:
        logger.error(f"Не удалось обработать документ: {e}")
        raise HTTPException(
            status_code=400, detail=f"Не удалось обработать документ: {e}"
        )


@router.get("/health")
async def kb_health():
    """Проверка работоспособности KB сервиса."""
    return {"status": "ok", "embedding_model": get_kb_config().embedding_model}


@router.post("/import-to-lightrag")
async def import_to_lightrag(
    version_id: Optional[str] = None,
    notes: str = "",
) -> dict:
    """Импортировать чанки в LightRAG с версионированием.

    Pipeline:
    1. Создать версию индекса
    2. Дедупликация по content_hash
    3. Индексация в LightRAG
    4. Извлечение сущностей и связей (Knowledge Graph)
    """
    import os

    try:
        from qa.lightrag_import import import_chunks_to_lightrag

        result = await import_chunks_to_lightrag(
            chunk_ids=None,
            limit=None,
            version_id=version_id,
            notes=notes,
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Import to LightRAG failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/rebuild-knowledge-graph")
async def rebuild_knowledge_graph(version_id: Optional[str] = None) -> dict:
    """Перестроить Knowledge Graph (только граф, без переиндексации чанков)."""
    try:
        from qa.lightrag_import import rebuild_knowledge_graph

        result = await rebuild_knowledge_graph(version_id=version_id)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Knowledge graph rebuild failed: {e}")
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}")


@router.get("/index-status")
async def get_index_status() -> dict:
    """Получить статус текущего индекса LightRAG."""
    try:
        from qa.lightrag_import import get_index_status

        return get_index_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index-versions")
async def list_index_versions(limit: int = 10) -> dict:
    """Список версий индекса."""
    try:
        from qa.lightrag_import import list_index_versions

        return {"versions": list_index_versions(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chunks/count")
async def get_chunks_count() -> dict:
    """Получить количество чанков в Базе Знаний."""
    engine = get_engine()

    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM chunks"))
        count = result.scalar()

    return {"count": count}
