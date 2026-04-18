"""API роуты для работы с Базой Знаний через LightRAG."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from qa.kb.parsers.web import WebPageParser


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["kb"])

_parser = WebPageParser()


class DocumentRequest(BaseModel):
    """Запрос на скачивание документа."""

    url: HttpUrl


class DocumentResponse(BaseModel):
    """Ответ со скачанным документом."""

    url: str
    title: str
    status: str


class ImportToLightRAGRequest(BaseModel):
    """Запрос на импорт в LightRAG."""

    chunk_ids: Optional[list[str]] = None
    limit: Optional[int] = None
    version_id: Optional[str] = None
    notes: str = ""


@router.post("/documents", response_model=DocumentResponse)
async def download_document(request: DocumentRequest) -> DocumentResponse:
    """Скачать и распарсить веб-страницу или PDF, затем импортировать в LightRAG.

    Args:
        request: DocumentRequest с URL документа для скачивания

    Returns:
        DocumentResponse с информацией о распарсенном документе
    """
    from qa.main import get_lightrag, is_lightrag_ready

    try:
        if not is_lightrag_ready():
            raise HTTPException(status_code=503, detail="LightRAG not initialized")

        parsed = await _parser.parse(str(request.url))
        logger.info(f"Распарсен документ: {parsed.title}")

        rag = get_lightrag()

        content = f"{parsed.title}\n\n{parsed.text_content}"
        doc_id = str(request.url)

        await rag.ainsert(
            [content],
            ids=[doc_id],
            file_paths=[str(request.url)],
        )

        return DocumentResponse(
            url=parsed.url,
            title=parsed.title,
            status="indexed",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось обработать документ: {e}")
        raise HTTPException(
            status_code=400, detail=f"Не удалось обработать документ: {e}"
        )


@router.get("/health")
async def kb_health():
    """Проверка работоспособности KB сервиса."""
    from qa.main import is_lightrag_ready
    from qa.kb.config import get_kb_config

    return {
        "status": "ok" if is_lightrag_ready() else "lightrag_not_ready",
        "embedding_model": get_kb_config().embedding_model,
    }


@router.post("/import-to-lightrag")
async def import_to_lightrag(
    version_id: Optional[str] = None,
    notes: str = "",
) -> dict:
    """Импортировать документы в LightRAG.

    Pipeline:
    1. Создать версию индекса
    2. Дедупликация по content_hash
    3. Индексация в LightRAG
    4. Извлечение сущностей и связей (Knowledge Graph)
    """
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


@router.get("/documents/count")
async def get_documents_count() -> dict:
    """Полу количество документов в Базе Знаний (LightRAG)."""
    from sqlalchemy import create_engine, text
    from qa.main import is_lightrag_ready

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="LightRAG not initialized")

    engine = create_engine("postgresql://voproshalych:voproshalych@postgres:5432/voproshalych")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM lightrag_doc_full")
        )
        count = result.scalar()

    return {"count": count}