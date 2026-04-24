# Бенчмарк v2 (LightRAG) - chunk-level оценка

## Что оцениваем

Бенчмарк считает качество retrieval на уровне `chunk_id`, а не URL.

- ground truth: `chunk_id` из synthetic dataset
- импорт в LightRAG: те же `chunk_text` из synthetic dataset (202 записи)
- предсказание: `retrieved_chunk_ids` из `aquery_data`

Это позволяет проверять точность поиска именно по релевантному куску текста.

## Метрики

| Метрика | Описание |
|---------|----------|
| HitRate@1, @5, @10 | Доля запросов, где релевантный `chunk_id` в топ-K |
| MRR | Средний обратный ранг первого релевантного `chunk_id` |
| Recall@1, @3, @5, @10 | Доля найденных релевантных `chunk_id` |
| Precision@1, @3, @5, @10 | Доля релевантных `chunk_id` среди найденных |
| NDCG@5, @10 | Качество ранжирования с учетом позиции |

Для каждой метрики считается 95% CI (bootstrap, 1000 итераций).

## Быстрый запуск

Ниже команды из корня `Submodules/voproshalych_v2/`.

1) Поднять только нужные сервисы:

```bash
docker compose up -d --build postgres db-migrate qa-service
docker compose ps
```

2) Проверить ключ Mistral:

```bash
# Если ключ хранится в .env, команда ниже просто проверит наличие.
# Если нет — экспортируй вручную:
# export MISTRAL_API_KEY="<YOUR_TOKEN>"
test -n "$MISTRAL_API_KEY" && echo "MISTRAL_API_KEY is set"
```

3) Импортировать 202 чанка в LightRAG:

```bash
docker compose exec \
  -e LIGHT_RAG_LLM_MODEL=mistral \
  -e MISTRAL_API_KEY="${MISTRAL_API_KEY:?set MISTRAL_API_KEY}" \
  qa-service \
  uv run python -m benchmarks.import_to_lightrag \
    --dataset benchmarks/data/dataset/dataset_synthetic_20260223_183530.json \
    --clear
```

4) Запустить chunk-level бенчмарк:

```bash
docker compose exec \
  -e LIGHT_RAG_LLM_MODEL=mistral \
  -e MISTRAL_API_KEY="${MISTRAL_API_KEY:?set MISTRAL_API_KEY}" \
  qa-service \
  uv run python -m benchmarks.run_benchmark
```

Если видишь ошибки DNS/соединения (`NameResolutionError`, `RemoteDisconnected`),
это сеть/доступ к API Mistral, а не проблема chunk-level пайплайна.

Проверка доступа к Mistral из контейнера:

```bash
docker compose exec \
  -e MISTRAL_API_KEY="${MISTRAL_API_KEY:?set MISTRAL_API_KEY}" \
  qa-service \
  uv run python - <<'PY'
import asyncio
from qa.llm.providers.mistral import MistralProvider

async def main():
    p = MistralProvider()
    r = await p.generate(prompt="Ответь только ОК", temperature=0, max_tokens=16)
    print("OK:", (r.content or "")[:80])

asyncio.run(main())
PY
```

## Важные детали импорта

- Скрипт `benchmarks/import_to_lightrag.py` импортирует `chunk_text` one-to-one.
- Для возврата `chunk_id` в поиске в `file_path` сохраняется `dataset_chunk:<chunk_id>`.
- Для запрета повторного re-chunking на время импорта задаются:
  - `CHUNK_TOKEN_SIZE=8192`
  - `CHUNK_OVERLAP_TOKEN_SIZE=0`

То есть целевое состояние - ровно 202 чанка synthetic dataset.

## Полезные варианты запуска

Тест на первых 10 запросах:

```bash
docker compose exec \
  -e LIGHT_RAG_LLM_MODEL=mistral \
  -e MISTRAL_API_KEY="${MISTRAL_API_KEY:?set MISTRAL_API_KEY}" \
  qa-service \
  uv run python -m benchmarks.run_benchmark --limit 10
```

С query expansion:

```bash
docker compose exec \
  -e LIGHT_RAG_LLM_MODEL=mistral \
  -e MISTRAL_API_KEY="${MISTRAL_API_KEY:?set MISTRAL_API_KEY}" \
  qa-service \
  uv run python -m benchmarks.run_benchmark --query-expansion
```

Кастомный output:

```bash
docker compose exec \
  -e LIGHT_RAG_LLM_MODEL=mistral \
  -e MISTRAL_API_KEY="${MISTRAL_API_KEY:?set MISTRAL_API_KEY}" \
  qa-service \
  uv run python -m benchmarks.run_benchmark \
    --output benchmarks/data/results/benchmark_v2_final.json
```

## Формат результата

Файл: `benchmarks/data/results/benchmark_v2_<timestamp>.json`.

Ключевые поля:

- `benchmark_metadata.evaluation_level = "chunk_id"`
- `metrics.*`
- `confidence_intervals_95.*`
- `per_query_details[].ground_truth_chunk_ids`
- `per_query_details[].retrieved_chunk_ids`

Пример:

```json
{
  "benchmark_metadata": {
    "evaluation_level": "chunk_id",
    "dataset_size": 202,
    "evaluated_queries": 202
  },
  "metrics": {
    "hit_rate@1": 0.41,
    "mrr": 0.63
  },
  "per_query_details": [
    {
      "id": "syn_bb5a6fd765eb",
      "ground_truth_chunk_ids": ["92459"],
      "retrieved_chunk_ids": ["92459", "92501"]
    }
  ]
}
```

## Опционально: аудит дампа v1

Если нужно проверить соответствие dump и dataset:

```bash
cd qa-service
uv run python -m benchmarks.prepare_v1_documents \
  --dump ../../voproshalych/benchmarks/data/dump/virtassist_backup_20260228.dump
```

Скрипт создаст:

- `benchmarks/data/v1_chunks.json`
- `benchmarks/data/chunk_mapping.json`

Для самого chunk-level benchmark эти файлы не обязательны, потому что импорт
в LightRAG идет напрямую из synthetic dataset.
