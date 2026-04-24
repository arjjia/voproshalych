"""Парсер дампа v1: извлечение чанков и построение маппинга к датасету.

Читает SQL-дамп PostgreSQL (COPY-формат), извлекает все чанки
из таблицы chunk, строит маппинг chunk_id датасета → dump chunk
(по совпадению текста) и сохраняет:
- v1_chunks.json — 202 чанка для импорта в LightRAG
- chunk_mapping.json — маппинг dataset_chunk_id → dump_chunk_id

Использование:
    python -m benchmarks.prepare_v1_documents \
        --dump ../../voproshalych/benchmarks/data/dump/virtassist_backup_20260228.dump \
        --dataset benchmarks/data/dataset/dataset_synthetic_20260223_183530.json
"""

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _unescape_copy_text(text: str) -> str:
    """Декодировать экранирование COPY-формата PostgreSQL."""
    result = text.replace("\\n", "\n")
    result = result.replace("\\t", "\t")
    result = result.replace("\\r", "\r")
    result = result.replace("\\\\", "\\")
    return result


def parse_chunks_from_dump(dump_path: str) -> List[Dict]:
    """Извлечь все чанки из SQL-дампа.

    Парсит COPY-данные таблицы chunk, извлекая id, confluence_url, text.

    Args:
        dump_path: Путь к SQL-файлу дампа

    Returns:
        Список словарей {id, confluence_url, text}
    """
    chunks: List[Dict] = []
    in_copy = False
    copy_start_re = re.compile(r"COPY public\.chunk\s+\(", re.IGNORECASE)

    logger.info("Парсинг дампа: %s", dump_path)

    with open(dump_path, "r", encoding="utf-8") as f:
        for line in f:
            if not in_copy:
                if copy_start_re.search(line):
                    in_copy = True
                    logger.info("Найден COPY-блок таблицы chunk")
                continue

            if line.rstrip("\n").rstrip("\r") == "\\.":
                logger.info("Конец COPY-блока")
                break

            parts = line.split("\t")
            if len(parts) < 3:
                continue

            try:
                chunk_id = int(parts[0])
                url = parts[1]
                raw_text = parts[2]
                text = _unescape_copy_text(raw_text)

                chunks.append(
                    {
                        "id": chunk_id,
                        "confluence_url": url,
                        "text": text,
                    }
                )
            except (ValueError, IndexError):
                continue

    logger.info("Извлечено %d чанков из дампа", len(chunks))
    return chunks


def build_chunk_mapping(
    dump_chunks: List[Dict],
    dataset: List[Dict],
) -> Dict[str, str]:
    """Построить маппинг dataset_chunk_id → dump_chunk_id.

    Мэтчит по URL + сходству текста с ограничением уникальности:
    один dump chunk не может быть сопоставлен двум dataset chunk_id.
    В датасете chunk_text обычно обрезан до 500 символов, поэтому
    используется startswith/contains/длина общего префикса.

    Args:
        dump_chunks: Чанки из дампа [{id, confluence_url, text}]
        dataset: Записи датасета [{chunk_id, chunk_text, ...}]

    Returns:
        Словарь {dataset_chunk_id (str): dump_chunk_id (str)}
    """

    def _lcp_len(a: str, b: str) -> int:
        max_len = min(len(a), len(b))
        i = 0
        while i < max_len and a[i] == b[i]:
            i += 1
        return i

    dump_by_url: Dict[str, List[Dict]] = {}
    for chunk in dump_chunks:
        url = chunk.get("confluence_url", "")
        dump_by_url.setdefault(url, []).append(chunk)

    used_dump_ids: set[int] = set()

    mapping: Dict[str, str] = {}
    unmatched = 0

    for item in dataset:
        ds_chunk_id = str(item["chunk_id"])
        ds_url = item.get("confluence_url", "")
        ds_text = str(item.get("chunk_text", ""))

        candidates = [
            c for c in dump_by_url.get(ds_url, []) if int(c["id"]) not in used_dump_ids
        ]

        if not candidates:
            unmatched += 1
            logger.warning(
                "Не найден чанк в дампе для dataset chunk_id=%s",
                ds_chunk_id,
            )
            continue

        def _score(candidate: Dict) -> tuple[int, int]:
            cand_text = str(candidate.get("text", ""))
            if cand_text == ds_text:
                return (3, len(ds_text))
            if cand_text.startswith(ds_text):
                return (2, len(ds_text))
            if ds_text in cand_text:
                return (1, len(ds_text))
            return (0, _lcp_len(cand_text, ds_text))

        best = max(candidates, key=_score)
        score_rank, score_len = _score(best)

        if score_rank == 0 and score_len < 40:
            unmatched += 1
            logger.warning(
                "Слабое совпадение для chunk_id=%s (lcp=%d), пропуск",
                ds_chunk_id,
                score_len,
            )
            continue

        dump_id = int(best["id"])
        used_dump_ids.add(dump_id)
        mapping[ds_chunk_id] = str(dump_id)

    logger.info(
        "Маппинг: %d/%d совпадений, %d не найдено",
        len(mapping),
        len(dataset),
        unmatched,
    )
    return mapping


def main():
    """Главная функция CLI-скрипта."""
    parser = argparse.ArgumentParser(
        description="Извлечь чанки из дампа v1 и построить маппинг к датасету"
    )
    parser.add_argument(
        "--dump",
        type=str,
        required=True,
        help="Путь к SQL-файлу дампа БД v1",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="benchmarks/data/dataset/dataset_synthetic_20260223_183530.json",
        help="Путь к синтетическому датасету",
    )
    parser.add_argument(
        "--output-chunks",
        type=str,
        default="benchmarks/data/v1_chunks.json",
        help="Путь к выходному JSON с чанками",
    )
    parser.add_argument(
        "--output-mapping",
        type=str,
        default="benchmarks/data/chunk_mapping.json",
        help="Путь к выходному JSON с маппингом",
    )

    args = parser.parse_args()

    if not Path(args.dump).exists():
        logger.error("Файл дампа не найден: %s", args.dump)
        return

    dump_chunks = parse_chunks_from_dump(args.dump)
    if not dump_chunks:
        logger.error("Не удалось извлечь чанки из дампа")
        return

    for_export = [
        {
            "dump_id": c["id"],
            "confluence_url": c["confluence_url"],
            "text": c["text"],
        }
        for c in dump_chunks
    ]

    dataset = []
    if Path(args.dataset).exists():
        with open(args.dataset, "r", encoding="utf-8") as f:
            dataset = json.load(f)
        logger.info("Загружен датасет: %d записей", len(dataset))
    else:
        logger.warning("Датасет не найден: %s", args.dataset)

    mapping = build_chunk_mapping(dump_chunks, dataset)

    out_chunks = Path(args.output_chunks)
    out_chunks.parent.mkdir(parents=True, exist_ok=True)
    with open(out_chunks, "w", encoding="utf-8") as f:
        json.dump(for_export, f, ensure_ascii=False, indent=2)
    logger.info("Сохранено %d чанков в %s", len(for_export), out_chunks)

    out_mapping = Path(args.output_mapping)
    with open(out_mapping, "w", encoding="utf-8") as f:
        json.dump(
            {
                "description": "dataset_chunk_id → dump_chunk_id",
                "total": len(mapping),
                "mapping": mapping,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("Сохранён маппинг %d записей в %s", len(mapping), out_mapping)

    print(f"\nЧанков из дампа: {len(dump_chunks)}")
    print(f"Записей датасета: {len(dataset)}")
    print(f"Маппинг: {len(mapping)}/{len(dataset)}")
    print(f"Чанки: {out_chunks}")
    print(f"Маппинг: {out_mapping}")


if __name__ == "__main__":
    main()
