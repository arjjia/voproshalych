"""API роуты для работы с Базой Знаний через LightRAG."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from qa.kb.parsers.web import WebPageParser


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["kb"])

_parser = WebPageParser()


class DocumentRequest(BaseModel):
    url: HttpUrl


class DocumentResponse(BaseModel):
    url: str
    title: str
    status: str


@router.post("/documents", response_model=DocumentResponse)
async def download_document(request: DocumentRequest) -> DocumentResponse:
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
    from qa.main import is_lightrag_ready
    from qa.kb.config import get_kb_config

    return {
        "status": "ok" if is_lightrag_ready() else "lightrag_not_ready",
        "embedding_model": get_kb_config().embedding_model,
    }


@router.get("/stats")
async def get_kb_stats() -> dict:
    from sqlalchemy import create_engine, text
    from qa.main import is_lightrag_ready

    if not is_lightrag_ready():
        raise HTTPException(status_code=503, detail="LightRAG not initialized")

    engine = create_engine(
        "postgresql://voproshalych:voproshalych@postgres:5432/voproshalych"
    )

    with engine.connect() as conn:
        tables = {
            "documents": "lightrag_doc_full",
            "chunks": "lightrag_doc_chunks",
            "entities": "lightrag_full_entities",
            "relations": "lightrag_full_relations",
        }
        counts = {}
        for name, table in tables.items():
            try:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                counts[name] = result.scalar()
            except Exception:
                counts[name] = 0

    return counts
