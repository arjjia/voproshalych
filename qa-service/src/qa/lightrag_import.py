"""Bridge: импорт чанков из chunks/embeddings в LightRAG с версионированием."""

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

_engine = None

LIGHTRAG_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS lightrag_index_versions (
    version_id VARCHAR(50) PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,
    model_name VARCHAR(100),
    chunks_processed INTEGER DEFAULT 0,
    chunks_skipped INTEGER DEFAULT 0,
    chunks_failed INTEGER DEFAULT 0,
    error_log TEXT,
    notes TEXT
);
"""

LIGHTRAG_DOC_TABLE = """
CREATE TABLE IF NOT EXISTS lightrag_doc_registry (
    chunk_id VARCHAR(50) PRIMARY KEY,
    content_hash VARCHAR(64) NOT NULL,
    last_indexed_version VARCHAR(50),
    last_indexed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
);
"""


def _get_engine():
    global _engine
    if _engine is None:
        db_url = "postgresql://voproshalych:voproshalych@postgres:5432/voproshalych"
        _engine = create_engine(db_url)
    return _engine


def _ensure_tables():
    """Создать таблицы версионирования если не существуют."""
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text(LIGHTRAG_VERSION_TABLE))
        conn.execute(text(LIGHTRAG_DOC_TABLE))
        conn.commit()
    logger.info("Ensured lightrag versioning tables exist")


def _compute_hash(text: str) -> str:
    """Вычислить SHA256 хеш текста."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _create_version(version_id: Optional[str] = None, notes: str = "") -> str:
    """Создать новую версию индекса."""
    engine = _get_engine()
    vid = (
        version_id
        or f"v-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO lightrag_index_versions (version_id, status, notes)
                VALUES (:vid, 'running', :notes)
                ON CONFLICT (version_id) DO NOTHING
            """),
            {"vid": vid, "notes": notes},
        )
        conn.commit()

    logger.info(f"Created index version: {vid}")
    return vid


def _update_version(
    version_id: str,
    status: str,
    processed: int = 0,
    skipped: int = 0,
    failed: int = 0,
    error_log: str = "",
):
    """Обновить статус версии индекса."""
    engine = _get_engine()

    with engine.connect() as conn:
        if status in ("completed", "failed"):
            conn.execute(
                text("""
                    UPDATE lightrag_index_versions 
                    SET status = :status, 
                        finished_at = NOW(),
                        chunks_processed = :processed,
                        chunks_skipped = :skipped,
                        chunks_failed = :failed,
                        error_log = :error_log
                    WHERE version_id = :vid
                """),
                {
                    "status": status,
                    "processed": processed,
                    "skipped": skipped,
                    "failed": failed,
                    "error_log": error_log[:5000] if error_log else None,
                    "vid": version_id,
                },
            )
        else:
            conn.execute(
                text("""
                    UPDATE lightrag_index_versions 
                    SET chunks_processed = :processed,
                        chunks_skipped = :skipped,
                        chunks_failed = :failed
                    WHERE version_id = :vid
                """),
                {
                    "processed": processed,
                    "skipped": skipped,
                    "failed": failed,
                    "vid": version_id,
                },
            )
        conn.commit()


def get_existing_chunks(limit: Optional[int] = None) -> list[dict]:
    """Получить чанки из БД."""
    engine = _get_engine()

    query = """
        SELECT c.id, c.text, c.title, c.source_url, c.source_type
        FROM chunks c
        ORDER BY c.created_at
    """

    if limit:
        query += f" LIMIT {limit}"

    with engine.connect() as conn:
        result = conn.execute(text(query))

        chunks = []
        for row in result:
            chunks.append(
                {
                    "id": str(row.id),
                    "text": row.text,
                    "title": row.title or "Untitled",
                    "source_url": row.source_url,
                    "source_type": row.source_type,
                }
            )

    logger.info(f"Retrieved {len(chunks)} chunks from database")
    return chunks


def get_full_documents(limit: Optional[int] = None) -> list[dict]:
    """Получить полные документы из БД (группировка по source_url).

    Объединяет все чанки одного документа в один текст для передачи в LightRAG.
    """
    engine = _get_engine()

    query = """
        SELECT c.source_url, c.title, string_agg(c.text, ' ' ORDER BY c.created_at) as full_text, c.source_type
        FROM chunks c
        GROUP BY c.source_url, c.title, c.source_type
        ORDER BY MIN(c.created_at)
    """

    if limit:
        query += f" LIMIT {limit}"

    with engine.connect() as conn:
        result = conn.execute(text(query))

        documents = []
        for row in result:
            documents.append({
                "id": row.source_url or str(row.source_url),
                "title": row.title or "Untitled",
                "full_text": row.full_text or "",
                "source_url": row.source_url,
                "source_type": row.source_type,
            })

    logger.info(f"Retrieved {len(documents)} full documents from database")
    return documents


async def import_chunks_to_lightrag(
    chunk_ids: Optional[list[str]] = None,
    limit: Optional[int] = None,
    version_id: Optional[str] = None,
    notes: str = "",
    use_full_documents: bool = True,
) -> dict:
    """Импортировать документы в LightRAG с версионированием.

    Использует Вариант А: LightRAG сам режет документы через chunk_token_size.
    Передаём полные документы (объединённые чанки), LightRAG сам нарежет на чанки.
    """
    from .lightrag_adapter import create_lightrag_config
    from .main import get_lightrag, is_lightrag_ready

    _ensure_tables()

    if not is_lightrag_ready():
        raise RuntimeError(
            "LightRAG not initialized or not ready"
        )

    rag = get_lightrag()
    config = create_lightrag_config()
    chunk_token_size = config.get("chunk_token_size", 1024)

    vid = _create_version(version_id, notes)

    logger.info(
        f"Starting import for version {vid} (full_documents={use_full_documents}, chunk_token_size={chunk_token_size})..."
    )

    if chunk_ids:
        logger.warning("chunk_ids parameter is ignored in full-document import mode")

    documents = get_full_documents(limit=limit)

    if not documents:
        _update_version(vid, "completed", 0, 0, 0)
        return {"status": "no_documents", "imported": 0, "version_id": vid}

    processed = 0
    skipped = 0
    failed = 0

    documents_list: list[str] = []
    ids_list: list[str] = []
    file_paths_list: list[str] = []
    docs_to_process: list[tuple[str, str, str]] = []

    engine = _get_engine()

    with engine.connect() as conn:
        for doc in documents:
            source_url = doc.get("source_url", "") or ""
            title = doc.get("title", "Untitled") or "Untitled"
            full_text = doc.get("full_text", "") or ""
            content = f"{title}\n\n{full_text}"

            doc_key_payload = f"{source_url}|{title}"
            doc_key = hashlib.sha1(doc_key_payload.encode("utf-8")).hexdigest()
            content_hash = _compute_hash(content)

            existing = conn.execute(
                text(
                    "SELECT content_hash FROM lightrag_doc_registry WHERE chunk_id = :cid"
                ),
                {"cid": doc_key},
            ).fetchone()

            if existing and existing[0] == content_hash:
                skipped += 1
                continue

            documents_list.append(content)
            ids_list.append(doc_key)
            file_paths_list.append(source_url)
            docs_to_process.append((doc_key, content_hash, source_url))
            processed += 1

    try:
        if documents_list:
            await rag.ainsert(
                documents_list,
                ids=ids_list,
                file_paths=file_paths_list,
            )

            with engine.connect() as conn:
                for doc_key, content_hash, _source_url in docs_to_process:
                    conn.execute(
                        text(
                            """
                            INSERT INTO lightrag_doc_registry (chunk_id, content_hash, last_indexed_version, status)
                            VALUES (:cid, :hash, :vid, 'indexed')
                            ON CONFLICT (chunk_id) DO UPDATE SET
                                content_hash = EXCLUDED.content_hash,
                                last_indexed_version = EXCLUDED.last_indexed_version,
                                last_indexed_at = NOW(),
                                status = 'indexed'
                            """
                        ),
                        {"cid": doc_key, "hash": content_hash, "vid": vid},
                    )
                conn.commit()

        _update_version(vid, "completed", processed, skipped, failed)

        logger.info(
            f"Import completed: {processed} processed, {skipped} skipped, {failed} failed"
        )

        return {
            "status": "success",
            "version_id": vid,
            "imported": processed,
            "skipped": skipped,
            "failed": failed,
            "message": f"Indexed {processed} documents. Skipped {skipped} unchanged.",
        }

    except Exception as e:
        error_msg = str(e)[:2000]
        _update_version(vid, "failed", processed, skipped, failed, error_msg)
        logger.error(f"Import failed: {e}")
        raise RuntimeError(f"Import failed: {e}")


async def rebuild_knowledge_graph(version_id: Optional[str] = None) -> dict:
    """Перестроить knowledge graph."""
    from .main import get_lightrag, is_lightrag_ready

    if not is_lightrag_ready():
        raise RuntimeError("LightRAG not initialized")

    rag = get_lightrag()
    vid = version_id or f"kg-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    logger.info(f"Starting knowledge graph extraction for version {vid}...")

    try:
        await rag.aextract_entities()

        logger.info("Knowledge graph built successfully")

        return {
            "status": "success",
            "version_id": vid,
            "message": "Knowledge graph built successfully",
        }

    except Exception as e:
        logger.error(f"Knowledge graph build failed: {e}")
        raise RuntimeError(f"KG build failed: {e}")


def get_index_status() -> dict:
    """Получить статус текущего индекса."""
    engine = _get_engine()

    with engine.connect() as conn:
        latest = conn.execute(
            text(
                "SELECT * FROM lightrag_index_versions ORDER BY created_at DESC LIMIT 1"
            )
        ).fetchone()

        if not latest:
            return {"status": "no_index", "message": "No index version found"}

        return {
            "version_id": latest[0],
            "status": latest[1],
            "created_at": str(latest[2]),
            "finished_at": str(latest[3]) if latest[3] else None,
            "model_name": latest[4],
            "chunks_processed": latest[5],
            "chunks_skipped": latest[6],
            "chunks_failed": latest[7],
            "error_log": latest[8],
            "notes": latest[9],
        }


def list_index_versions(limit: int = 10) -> list[dict]:
    """Список версий индекса."""
    engine = _get_engine()

    with engine.connect() as conn:
        results = conn.execute(
            text(
                "SELECT * FROM lightrag_index_versions ORDER BY created_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()

        versions = []
        for row in results:
            versions.append(
                {
                    "version_id": row[0],
                    "status": row[1],
                    "created_at": str(row[2]),
                    "finished_at": str(row[3]) if row[3] else None,
                    "model_name": row[4],
                    "chunks_processed": row[5],
                    "chunks_skipped": row[6],
                    "chunks_failed": row[7],
                }
            )

        return versions
