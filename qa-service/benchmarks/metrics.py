"""Вычисление метрик качества информационного поиска.

Метрики соответствуют стандартам TREC, BEIR, MTEB:
HitRate@K, MRR, NDCG@K, Recall@K, Precision@K.
"""

import math
from typing import Dict, List, Set, Tuple

import numpy as np


def _unique_preserve_order(urls: List[str]) -> List[str]:
    """Удалить дубликаты URL, сохранив порядок первого появления."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def hit_rate_at_k(
    retrieved_urls: List[str],
    relevant_urls: Set[str],
    k: int,
) -> float:
    """Вычислить HitRate@K.

    Доля запросов, для которых хотя бы один релевантный документ
    присутствует среди первых K результатов.

    Args:
        retrieved_urls: Список URL найденных документов (в порядке ранжирования)
        relevant_urls: Множество релевантных URL (ground truth)
        k: Количество top-K результатов

    Returns:
        1.0 если хотя бы один релевантный документ в top-K, иначе 0.0
    """
    if not relevant_urls:
        return 0.0
    top_k = set(_unique_preserve_order(retrieved_urls)[:k])
    return 1.0 if top_k & relevant_urls else 0.0


def reciprocal_rank(
    retrieved_urls: List[str],
    relevant_urls: Set[str],
) -> float:
    """Вычислить Reciprocal Rank для одного запроса.

    Обратный ранг первого релевантного документа.

    Args:
        retrieved_urls: Список URL найденных документов
        relevant_urls: Множество релевантных URL

    Returns:
        1/rank первого релевантного документа или 0.0
    """
    if not relevant_urls:
        return 0.0
    for i, url in enumerate(_unique_preserve_order(retrieved_urls), 1):
        if url in relevant_urls:
            return 1.0 / i
    return 0.0


def recall_at_k(
    retrieved_urls: List[str],
    relevant_urls: Set[str],
    k: int,
) -> float:
    """Вычислить Recall@K.

    Доля найденных релевантных документов от общего числа релевантных.

    Args:
        retrieved_urls: Список URL найденных документов
        relevant_urls: Множество релевантных URL
        k: Количество top-K результатов

    Returns:
        Доля релевантных документов в top-K
    """
    if not relevant_urls:
        return 0.0
    top_k = set(_unique_preserve_order(retrieved_urls)[:k])
    return len(top_k & relevant_urls) / len(relevant_urls)


def precision_at_k(
    retrieved_urls: List[str],
    relevant_urls: Set[str],
    k: int,
) -> float:
    """Вычислить Precision@K.

    Доля релевантных документов среди top-K.

    Args:
        retrieved_urls: Список URL найденных документов
        relevant_urls: Множество релевантных URL
        k: Количество top-K результатов

    Returns:
        Доля релевантных документов в top-K
    """
    if k == 0:
        return 0.0
    top_k = set(_unique_preserve_order(retrieved_urls)[:k])
    return len(top_k & relevant_urls) / k


def ndcg_at_k(
    retrieved_urls: List[str],
    relevant_urls: Set[str],
    k: int,
) -> float:
    """Вычислить NDCG@K (Normalized Discounted Cumulative Gain).

    Учитывает и наличие релевантных документов, и их позиции
    с дисконтированием. Все релевантные документы считаются
    равнозначными (gain = 1).

    Args:
        retrieved_urls: Список URL найденных документов
        relevant_urls: Множество релевантных URL
        k: Количество top-K результатов

    Returns:
        NDCG@K от 0.0 до 1.0
    """
    dedup = _unique_preserve_order(retrieved_urls)
    if k == 0 or not dedup:
        return 0.0

    dcg = 0.0
    for i, url in enumerate(dedup[:k], 1):
        gain = 1.0 if url in relevant_urls else 0.0
        dcg += gain / math.log2(i + 1)

    ideal_dcg = 0.0
    for i in range(1, min(k, len(relevant_urls)) + 1):
        ideal_dcg += 1.0 / math.log2(i + 1)

    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


K_VALUES = [1, 3, 5, 10]

METRIC_NAMES = [
    "hit_rate@1",
    "hit_rate@5",
    "hit_rate@10",
    "mrr",
    "recall@1",
    "recall@3",
    "recall@5",
    "recall@10",
    "precision@1",
    "precision@3",
    "precision@5",
    "precision@10",
    "ndcg@5",
    "ndcg@10",
]

V1_BASELINE: Dict[str, float] = {
    "hit_rate@1": 0.3465,
    "hit_rate@5": 0.6634,
    "hit_rate@10": 0.7871,
    "mrr": 0.5945,
    "recall@1": 0.4307,
    "recall@3": 0.7079,
    "recall@5": 0.8317,
    "recall@10": 0.9307,
    "precision@1": 0.4307,
    "precision@3": 0.2360,
    "precision@5": 0.1663,
    "precision@10": 0.0931,
    "ndcg@5": 0.8681,
    "ndcg@10": 0.8681,
}


def compute_per_query_metrics(
    retrieved_urls: List[str],
    relevant_urls: Set[str],
) -> Dict[str, float]:
    """Вычислить все метрики для одного запроса.

    Args:
        retrieved_urls: Список URL найденных документов
        relevant_urls: Множество релевантных URL

    Returns:
        Словарь с метриками для одного запроса
    """
    result: Dict[str, float] = {}
    for k in K_VALUES:
        result[f"hit_rate@{k}"] = hit_rate_at_k(retrieved_urls, relevant_urls, k)
        result[f"recall@{k}"] = recall_at_k(retrieved_urls, relevant_urls, k)
        result[f"precision@{k}"] = precision_at_k(retrieved_urls, relevant_urls, k)
    result["mrr"] = reciprocal_rank(retrieved_urls, relevant_urls)
    result["ndcg@5"] = ndcg_at_k(retrieved_urls, relevant_urls, 5)
    result["ndcg@10"] = ndcg_at_k(retrieved_urls, relevant_urls, 10)
    return result


def compute_aggregate_metrics(
    per_query_list: List[Dict[str, float]],
) -> Dict[str, float]:
    """Усреднить метрики по всем запросам.

    Args:
        per_query_list: Список словарей с метриками для каждого запроса

    Returns:
        Усреднённые метрики
    """
    if not per_query_list:
        return {name: 0.0 for name in METRIC_NAMES}
    result: Dict[str, float] = {}
    for name in METRIC_NAMES:
        values = [q[name] for q in per_query_list if name in q]
        result[name] = float(np.mean(values)) if values else 0.0
    return result


def bootstrap_ci(
    per_query_list: List[Dict[str, float]],
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> Dict[str, Dict[str, float]]:
    """Вычислить доверительные интервалы через bootstrap.

    Args:
        per_query_list: Список словарей с метриками для каждого запроса
        n_boot: Количество bootstrap-итераций
        ci: Уровень доверительного интервала
        seed: Seed для воспроизводимости

    Returns:
        Словарь {metric_name: {mean, ci_low, ci_high}}
    """
    rng = np.random.default_rng(seed)
    n = len(per_query_list)
    if n == 0:
        return {
            name: {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0} for name in METRIC_NAMES
        }

    alpha = (1.0 - ci) / 2.0
    boot_samples: Dict[str, List[float]] = {name: [] for name in METRIC_NAMES}

    for _ in range(n_boot):
        indices = rng.integers(0, n, size=n)
        sample = [per_query_list[i] for i in indices]
        agg = compute_aggregate_metrics(sample)
        for name in METRIC_NAMES:
            boot_samples[name].append(agg[name])

    result: Dict[str, Dict[str, float]] = {}
    for name in METRIC_NAMES:
        values = boot_samples[name]
        result[name] = {
            "mean": float(np.mean(values)),
            "ci_low": float(np.percentile(values, alpha * 100)),
            "ci_high": float(np.percentile(values, (1 - alpha) * 100)),
        }
    return result


def compute_comparison_table(
    v2_metrics: Dict[str, float],
    v1_baseline: Dict[str, float] | None = None,
) -> List[Dict[str, object]]:
    """Сформировать таблицу сравнения v1 и v2 для статьи.

    Args:
        v2_metrics: Метрики v2 (LightRAG)
        v1_baseline: Метрики v1 (Naive RAG), по умолчанию V1_BASELINE

    Returns:
        Список словарей с метриками v1, v2 и дельтой
    """
    baseline = v1_baseline or V1_BASELINE
    rows: List[Dict[str, object]] = []
    for name in METRIC_NAMES:
        v1_val = baseline.get(name, 0.0)
        v2_val = v2_metrics.get(name, 0.0)
        delta = v2_val - v1_val
        rows.append(
            {
                "metric": name,
                "v1_naive_rag": round(v1_val, 4),
                "v2_lightrag": round(v2_val, 4),
                "delta": round(delta, 4),
            }
        )
    return rows
