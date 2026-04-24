"""CLI-скрипт для запуска chunk-level бенчмарка v2 (LightRAG).

Вычисляет метрики качества поиска HitRate@K, MRR, NDCG@K,
Recall@K, Precision@K на синтетическом датасете и сохраняет
результаты в JSON.

Оценка проводится на уровне chunk_id (не URL).

Поддерживаемые режимы поиска (param --search-mode):
- naive: чистый векторный поиск (аналог v1, без графа)
- local: поиск через сущности графа
- global: поиск через отношения графа
- hybrid: local + global
- mix: hybrid + векторный поиск (по умолчанию)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

import numpy as np
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _load_dataset(path: str) -> List[Dict]:
    """Загрузить синтетический датасет из JSON."""
    logger.info("Загрузка датасета: %s", path)
    with open(path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    logger.info("Загружено %d записей", len(dataset))
    return dataset


def _extract_ground_truth_chunk_ids(item: Dict) -> Set[str]:
    """Извлечь ground truth chunk_id из записи датасета."""
    chunk_ids: Set[str] = set()

    chunk_id = item.get("chunk_id")
    if chunk_id is not None:
        chunk_ids.add(str(chunk_id).strip())

    relevant = item.get("relevant_chunk_ids")
    if isinstance(relevant, list):
        for cid in relevant:
            if cid is not None:
                chunk_ids.add(str(cid).strip())

    return {cid for cid in chunk_ids if cid}


async def run_benchmark(
    dataset: List[Dict],
    top_k: int = 10,
    search_mode: str = "mix",
    cosine_threshold: float | None = None,
    use_query_expansion: bool = False,
    delay_between_queries: float = 1.0,
) -> Dict:
    """Запустить chunk-level бенчмарк v2.

    Args:
        dataset: Список записей из синтетического датасета
        top_k: Количество результатов поиска
        search_mode: Режим LightRAG (naive/local/global/hybrid/mix)
        cosine_threshold: Порог косинусного сходства (None=default)
        use_query_expansion: Использовать расширение запросов
        delay_between_queries: Задержка между запросами (секунды)

    Returns:
        Словарь с результатами бенчмарка
    """
    from lightrag import QueryParam
    from qa.lightrag_adapter import (
        create_lightrag_instance,
        extract_chunk_ids_from_search_data,
    )

    from benchmarks.metrics import (
        METRIC_NAMES,
        V1_BASELINE,
        bootstrap_ci,
        compute_aggregate_metrics,
        compute_comparison_table,
        compute_per_query_metrics,
    )

    if cosine_threshold is not None:
        os.environ["COSINE_THRESHOLD"] = str(cosine_threshold)
        logger.info("COSINE_THRESHOLD переопределён: %s", cosine_threshold)

    rag = await create_lightrag_instance()

    per_query_metrics: List[Dict[str, float]] = []
    per_query_details: List[Dict] = []
    errors = 0
    total = len(dataset)

    logger.info(
        "Запуск chunk-level бенчмарка: %d запросов, top_k=%d, "
        "mode=%s, cosine_threshold=%s, query_expansion=%s",
        total,
        top_k,
        search_mode,
        cosine_threshold,
        use_query_expansion,
    )

    for idx, item in enumerate(dataset):
        question = item["question"]
        ground_truth = _extract_ground_truth_chunk_ids(item)
        item_id = item.get("id", str(idx))

        if not ground_truth:
            logger.warning(
                "[%d/%d] %s: нет ground truth chunk_id, пропуск",
                idx + 1,
                total,
                item_id,
            )
            continue

        search_query = question
        if use_query_expansion:
            try:
                from qa.services.question_router import classify_and_expand

                classification = await classify_and_expand(
                    question,
                    request_id=f"bm-{item_id}",
                )
                search_query = classification.expanded_query or question
                logger.info(
                    "[%d/%d] Expanded: '%s' -> '%s'",
                    idx + 1,
                    total,
                    question[:60],
                    search_query[:60],
                )
            except Exception as exc:
                logger.warning(
                    "[%d/%d] Query expansion failed: %s",
                    idx + 1,
                    total,
                    exc,
                )

        try:
            param = QueryParam(
                mode=search_mode,
                top_k=top_k,
                only_need_context=True,
            )

            t0 = time.time()
            search_data = await rag.aquery_data(search_query, param=param)
            elapsed = time.time() - t0

            retrieved_chunk_ids = extract_chunk_ids_from_search_data(
                search_data, top_k
            )
            q_metrics = compute_per_query_metrics(
                retrieved_chunk_ids, ground_truth
            )
            per_query_metrics.append(q_metrics)

            per_query_details.append(
                {
                    "id": item_id,
                    "question": question,
                    "search_query": search_query,
                    "confluence_url": item.get("confluence_url"),
                    "ground_truth_chunk_ids": sorted(ground_truth),
                    "retrieved_chunk_ids": retrieved_chunk_ids,
                    "metrics": {k: round(v, 4) for k, v in q_metrics.items()},
                    "search_time_sec": round(elapsed, 2),
                }
            )

            logger.info(
                "[%d/%d] MRR=%.3f HR@5=%d recall@5=%.3f "
                "chunks=%d time=%.1fs '%s'",
                idx + 1,
                total,
                q_metrics["mrr"],
                int(q_metrics["hit_rate@5"]),
                q_metrics["recall@5"],
                len(retrieved_chunk_ids),
                elapsed,
                question[:50],
            )

        except Exception as exc:
            logger.error(
                "[%d/%d] Ошибка поиска: %s — '%s'",
                idx + 1,
                total,
                exc,
                question[:50],
            )
            errors += 1

        if delay_between_queries > 0 and idx < total - 1:
            await asyncio.sleep(delay_between_queries)

    n_evaluated = len(per_query_metrics)
    logger.info(
        "Поиск завершён: %d/%d успешно, %d ошибок",
        n_evaluated,
        total,
        errors,
    )

    aggregate = compute_aggregate_metrics(per_query_metrics)
    ci_results = bootstrap_ci(per_query_metrics)
    comparison = compute_comparison_table(aggregate, V1_BASELINE)

    search_times = [
        d["search_time_sec"] for d in per_query_details if "search_time_sec" in d
    ]

    result = {
        "benchmark_metadata": {
            "version": "v2-lightrag",
            "timestamp": datetime.now().isoformat(),
            "dataset_size": total,
            "evaluated_queries": n_evaluated,
            "errors": errors,
            "top_k": top_k,
            "search_mode": search_mode,
            "cosine_threshold": cosine_threshold or os.getenv(
                "COSINE_THRESHOLD", "0.2"
            ),
            "query_expansion": use_query_expansion,
            "evaluation_level": "chunk_id",
            "embedding_model": os.getenv(
                "LIGHT_RAG_MODEL_NAME",
                "nizamovtimur-multilingual-e5-large-wikiutmn",
            ),
            "llm_model": os.getenv("LIGHT_RAG_LLM_MODEL", "mistral"),
        },
        "metrics": {name: round(aggregate[name], 4) for name in METRIC_NAMES},
        "confidence_intervals_95": {
            name: {
                "mean": round(ci_results[name]["mean"], 4),
                "ci_low": round(ci_results[name]["ci_low"], 4),
                "ci_high": round(ci_results[name]["ci_high"], 4),
            }
            for name in METRIC_NAMES
        },
        "comparison_v1_v2": comparison,
        "timing": {
            "avg_search_time_sec": (
                round(float(np.mean(search_times)), 3) if search_times else 0.0
            ),
            "total_search_time_sec": round(sum(search_times), 1),
        },
        "per_query_details": per_query_details,
    }

    return result


def save_results(result: Dict, output_path: str) -> None:
    """Сохранить результаты бенчмарка в JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("Результаты сохранены: %s", output_path)


def print_summary(result: Dict) -> None:
    """Вывести краткую сводку результатов в консоль."""
    metrics = result["metrics"]
    ci = result["confidence_intervals_95"]
    meta = result["benchmark_metadata"]
    timing = result["timing"]
    comparison = result.get("comparison_v1_v2", [])

    print("\n" + "=" * 70)
    print(
        f"V2 (LightRAG) CHUNK-LEVEL BENCHMARK — N={meta['evaluated_queries']}"
    )
    print(
        f"mode={meta['search_mode']} top_k={meta['top_k']} "
        f"cosine={meta['cosine_threshold']}"
    )
    print("=" * 70)

    print(f"\n{'Метрика':<18} {'v2':>10} {'v1':>10} {'Δ':>8} {'95% CI':>24}")
    print("-" * 70)

    for row in comparison:
        name = row["metric"]
        v2_val = row["v2_lightrag"]
        v1_val = row["v1_naive_rag"]
        delta = row["delta"]
        ci_row = ci.get(name, {})
        ci_low = ci_row.get("ci_low", 0.0)
        ci_high = ci_row.get("ci_high", 0.0)
        delta_sign = "+" if delta >= 0 else ""
        print(
            f"{name:<18} {v2_val:>10.4f} {v1_val:>10.4f} "
            f"{delta_sign}{delta:>7.4f} [{ci_low:.4f}, {ci_high:.4f}]"
        )

    print("-" * 70)
    print(
        f"Среднее время поиска: {timing['avg_search_time_sec']:.3f}s "
        f"(всего: {timing['total_search_time_sec']:.1f}s)"
    )
    print("=" * 70 + "\n")


def main():
    """Главная функция CLI-скрипта."""
    default_dataset = str(
        Path(__file__).resolve().parent
        / "data"
        / "dataset"
        / "dataset_synthetic_20260223_183530.json"
    )
    parser = argparse.ArgumentParser(
        description=(
            "Бенчмарк v2 (LightRAG) — chunk-level "
            "метрики качества поиска"
        )
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=default_dataset,
        help="Путь к синтетическому датасету (JSON)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Путь к выходному JSON-файлу "
            "(по умолчанию: benchmarks/data/results/"
            "benchmark_v2_<ts>.json)"
        ),
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Количество результатов поиска (default: 10)",
    )
    parser.add_argument(
        "--search-mode",
        type=str,
        default="mix",
        choices=["naive", "local", "global", "hybrid", "mix"],
        help=(
            "Режим поиска LightRAG: "
            "naive (векторный), local, global, hybrid, mix (default: mix)"
        ),
    )
    parser.add_argument(
        "--cosine-threshold",
        type=float,
        default=None,
        help=(
            "Порог косинусного сходства для векторного поиска "
            "(default: 0.2)"
        ),
    )
    parser.add_argument(
        "--query-expansion",
        action="store_true",
        help="Использовать расширение запросов (query expansion)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Задержка между запросами в секундах (default: 1.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничение количества запросов из датасета",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Не включать per-query детали в JSON",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Путь к .env файлу (по умолчанию: .env.local-2 или .env)",
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

    dataset = _load_dataset(args.dataset)
    if args.limit:
        dataset = dataset[: args.limit]
        logger.info("Ограничение: %d запросов", len(dataset))

    result = asyncio.run(
        run_benchmark(
            dataset=dataset,
            top_k=args.top_k,
            search_mode=args.search_mode,
            cosine_threshold=args.cosine_threshold,
            use_query_expansion=args.query_expansion,
            delay_between_queries=args.delay,
        )
    )

    if args.no_details:
        result.pop("per_query_details", None)

    if args.output:
        output_path = args.output
    else:
        results_dir = str(
            Path(__file__).resolve().parent / "data" / "results"
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{results_dir}/benchmark_v2_{ts}.json"

    save_results(result, output_path)
    print_summary(result)


if __name__ == "__main__":
    main()
