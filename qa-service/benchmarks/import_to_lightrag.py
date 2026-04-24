"""Импорт chunk-level датасета в LightRAG (v2) без изменения гранулярности.

Источник данных — synthetic dataset (202 записей), где каждая запись
содержит `chunk_id` и `chunk_text`. Эти чанки импортируются в LightRAG
один-к-одному, чтобы бенчмарк сравнивался по тем же chunk_id.

Чтобы сохранить ровно 202 чанка, импорт выполняется с увеличенным
chunk_token_size (по умолчанию 8192), чтобы LightRAG не разбивал
входные тексты повторно.

Использование:
    python -m benchmarks.import_to_lightrag \
        --dataset benchmarks/data/dataset/dataset_synthetic_20260223_183530.json \
        --clear
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _load_chunks_from_dataset(dataset_path: str) -> list[dict]:
    """Загрузить чанки для импорта из synthetic dataset."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    chunks: list[dict] = []
    for item in dataset:
        chunk_id = str(item.get("chunk_id", "")).strip()
        chunk_text = item.get("chunk_text", "")
        confluence_url = item.get("confluence_url", "")
        if not chunk_id or not isinstance(chunk_text, str) or not chunk_text.strip():
            continue
        chunks.append(
            {
                "dataset_chunk_id": chunk_id,
                "text": chunk_text,
                "confluence_url": confluence_url,
            }
        )

    return chunks


async def import_chunks(
    dataset_path: str,
    clear: bool = False,
    limit: int | None = None,
    delay: float = 2.0,
) -> None:
    """Импортировать чанки в LightRAG.

    Args:
        dataset_path: Путь к synthetic dataset JSON
        clear: Очистить хранилище перед импортом
        limit: Ограничение количества чанков
        delay: Задержка между чанками (секунды)
    """
    from qa.lightrag_adapter import create_lightrag_instance

    logger.info("Загрузка датасета: %s", dataset_path)
    chunks = _load_chunks_from_dataset(dataset_path)

    if limit:
        chunks = chunks[:limit]
        logger.info("Ограничение: %d чанков", len(chunks))

    logger.info("Чанков для импорта: %d", len(chunks))

    if "CHUNK_TOKEN_SIZE" not in os.environ:
        os.environ["CHUNK_TOKEN_SIZE"] = "8192"
    if "CHUNK_OVERLAP_TOKEN_SIZE" not in os.environ:
        os.environ["CHUNK_OVERLAP_TOKEN_SIZE"] = "0"
    logger.info(
        "Chunk config for import: CHUNK_TOKEN_SIZE=%s, CHUNK_OVERLAP_TOKEN_SIZE=%s",
        os.getenv("CHUNK_TOKEN_SIZE"),
        os.getenv("CHUNK_OVERLAP_TOKEN_SIZE"),
    )

    rag = await create_lightrag_instance()

    if clear:
        logger.info("Очистка хранилищ LightRAG...")
        for storage in (
            rag.full_docs,
            rag.text_chunks,
            rag.full_entities,
            rag.full_relations,
            rag.entity_chunks,
            rag.relation_chunks,
            rag.entities_vdb,
            rag.relationships_vdb,
            rag.chunks_vdb,
            rag.chunk_entity_relation_graph,
            rag.llm_response_cache,
            rag.doc_status,
        ):
            if storage:
                await storage.drop()
        await rag.initialize_storages()
        logger.info("Хранилища очищены и переинициализированы")

    total = len(chunks)
    success = 0
    errors = 0
    start_time = time.time()

    for idx, chunk in enumerate(chunks):
        dataset_chunk_id = chunk["dataset_chunk_id"]
        text = chunk["text"]
        source_url = chunk.get("confluence_url", "")

        doc_key = f"benchmark_v1_chunk:{dataset_chunk_id}"
        doc_id = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]
        file_path = f"dataset_chunk:{dataset_chunk_id}"

        try:
            t0 = time.time()
            await rag.ainsert([text], ids=[doc_id], file_paths=[file_path])

            elapsed = time.time() - t0
            success += 1
            logger.info(
                "[%d/%d] OK: dataset_chunk=%s (%d символов, %.1fs)",
                idx + 1,
                total,
                dataset_chunk_id,
                len(text),
                elapsed,
            )

        except Exception as exc:
            errors += 1
            logger.error(
                "[%d/%d] FAIL: dataset_chunk=%s url=%s — %s",
                idx + 1,
                total,
                dataset_chunk_id,
                source_url[:80],
                exc,
            )

        if delay > 0 and idx < total - 1:
            await asyncio.sleep(delay)

    total_time = time.time() - start_time

    print(f"\n{'=' * 60}")
    print(f"Импорт завершён: {success}/{total} успешно, {errors} ошибок")
    print(f"Общее время: {total_time:.1f}s")
    print(f"Среднее на чанк: {total_time / max(total, 1):.1f}s")
    print(f"{'=' * 60}")


def main():
    """Главная функция CLI-скрипта."""
    parser = argparse.ArgumentParser(description="Импорт чанков в LightRAG v2")
    parser.add_argument(
        "--dataset",
        type=str,
        default=("benchmarks/data/dataset/" "dataset_synthetic_20260223_183530.json"),
        help="Путь к synthetic dataset JSON",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Очистить хранилище перед импортом",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничение количества чанков",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Задержка между чанками (секунды, default: 2.0)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Путь к .env файлу",
    )

    args = parser.parse_args()

    if args.env_file:
        load_dotenv(dotenv_path=args.env_file, override=True)
    else:
        for candidate in [".env.local-2", ".env"]:
            if os.path.exists(candidate):
                load_dotenv(dotenv_path=candidate, override=False)
                logger.info("Загружен env: %s", candidate)
                break

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

    asyncio.run(
        import_chunks(
            dataset_path=args.dataset,
            clear=args.clear,
            limit=args.limit,
            delay=args.delay,
        )
    )


if __name__ == "__main__":
    main()
