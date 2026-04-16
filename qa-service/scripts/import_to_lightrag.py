"""Скрипт для импорта документов в LightRAG и создания графа знаний.

Работает независимо от fill_kb_from_sources.py - требует чтобы БД уже содержала чанки.

Аргументы:
    --clear   Очистить хранилище LightRAG перед импортом ( НЕ трогает чанки в БД)
    --rebuild Перестроить граф знаний (извлечь сущности и связи заново)
    --limit   Ограничить количество документов для импорта

Примеры использования:
    # Очистить LightRAG и импортировать все документы из БД
    python scripts/import_to_lightrag.py --clear

    # Только импортировать (добавить к существующему)
    python scripts/import_to_lightrag.py

    # Импортировать и перестроить граф знаний
    python scripts/import_to_lightrag.py --clear --rebuild

    # Перестроить только граф (без повторного импорта)
    python scripts/import_to_lightrag.py --rebuild-only
"""

import argparse
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def clear_lightrag_storage():
    """Очистить только хранилище LightRAG, не трогая чанки в БД."""
    from sqlalchemy import create_engine, text

    engine = create_engine("postgresql://voproshalych:voproshalych@postgres:5432/voproshalych")

    tables = [
        "lightrag_doc_full",
        "lightrag_doc_chunks",
        "lightrag_doc_status",
        "lightrag_entity_chunks",
        "lightrag_full_entities",
        "lightrag_full_relations",
        "lightrag_relation_chunks",
        "lightrag_llm_cache",
    ]

    with engine.connect() as conn:
        for table in tables:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                logger.info(f"Cleared table: {table}")
            except Exception as e:
                logger.warning(f"Could not clear {table}: {e}")
        conn.commit()

    logger.info("LightRAG storage cleared (chunks table NOT touched)")


async def import_to_lightrag(limit: int | None = None):
    """Импортировать документы из БД в LightRAG."""
    from qa.lightrag_import import import_chunks_to_lightrag
    from qa.main import init_lightrag, is_lightrag_ready

    if not is_lightrag_ready():
        logger.info("Initializing LightRAG...")
        await init_lightrag()
        logger.info("LightRAG initialized")

    logger.info(f"Starting import to LightRAG (limit={limit})...")
    result = await import_chunks_to_lightrag(
        limit=limit,
        notes=f"CLI import, limit={limit}"
    )
    logger.info(f"Import result: {result}")
    return result


async def rebuild_knowledge_graph():
    """Перестроить граф знаний."""
    from qa.lightrag_import import rebuild_knowledge_graph
    from qa.main import init_lightrag, is_lightrag_ready

    if not is_lightrag_ready():
        logger.info("Initializing LightRAG...")
        await init_lightrag()
        logger.info("LightRAG initialized")

    logger.info("Starting knowledge graph rebuild...")
    result = await rebuild_knowledge_graph()
    logger.info(f"Knowledge graph result: {result}")
    return result


async def main(clear: bool, rebuild: bool, rebuild_only: bool, limit: int | None):
    logger.info("=" * 50)
    logger.info("LightRAG Import Tool")
    logger.info("=" * 50)

    if clear:
        logger.info("Step 1: Clearing LightRAG storage...")
        clear_lightrag_storage()

    if rebuild_only:
        logger.info("Step 1: Rebuilding knowledge graph only...")
        await rebuild_knowledge_graph()
    else:
        logger.info("Step 1: Importing documents to LightRAG...")
        await import_to_lightrag(limit=limit)

        if rebuild:
            logger.info("Step 2: Building knowledge graph...")
            await rebuild_knowledge_graph()

    logger.info("=" * 50)
    logger.info("Done!")
    logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Импорт в LightRAG и создание графа знаний")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить хранилище LightRAG перед импортом (НЕ трогает чанки)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Перестроить граф знаний после импорта",
    )
    parser.add_argument(
        "--rebuild-only",
        action="store_true",
        help="Только перестроить граф знаний (без повторного импорта)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество документов для импорта",
    )
    args = parser.parse_args()

    asyncio.run(main(args.clear, args.rebuild, args.rebuild_only, args.limit))