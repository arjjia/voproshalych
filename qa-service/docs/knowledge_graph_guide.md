# Гайд по созданию графа знаний (Knowledge Graph)

## Обзор

LightRAG использует **гибридный поиск**:
- **Векторный поиск** (pgvector) — семантическое сходство
- **Граф знаний** (Apache AGE) — связи между сущностями

При индексации документов LightRAG автоматически:
1. Разбивает документ на чанки (sentence-aware chunking, 500 токенов)
2. Создаёт эмбеддинги для векторного поиска (deepvk/USER-bge-m3, 1024-dim)
3. Извлекает **сущности** (entities) из текста через LLM
4. Извлекает **связи** (relations) между сущностями через LLM
5. Строит **граф знаний** в PostgreSQL (через Apache AGE)

## Какой LLM используется для графа?

Для индексации (entity extraction) используется **Ollama** с моделью `qwen3.6:35b` на удалённом сервере.

```bash
# Проверить доступность Ollama
curl -s http://iv-fc.orienteer.ru:12434/api/tags
```

Настроить в `.env`:
```bash
LIGHT_RAG_LLM_MODEL=ollama
OLLAMA_BASE_URL=http://iv-fc.orienteer.ru:12434
OLLAMA_MODEL=qwen3.6:35b
```

## Заполнение Базы Знаний

Подробнее: [KB_FILL_GUIDE.md](./KB_FILL_GUIDE.md)

```bash
# Полная переиндексация всех источников
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear

# Один источник
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source confluence_help

# Без построения графа (только чанки + эмбеддинги, быстрее)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --no-graph

# Инкрементально (конкретный URL)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py \
  --url "https://sveden.utmn.ru/sveden/managers/"
```

## Проверка графа

### Таблицы LightRAG в PostgreSQL

```bash
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "\dt" | grep lightrag
```

Должны быть таблицы:
- `lightrag_doc_full` — полные документы
- `lightrag_doc_chunks` — чанки
- `lightrag_full_entities` — сущности
- `lightrag_full_relations` — связи
- `lightrag_vdb_entity_*` — векторы сущностей
- `lightrag_vdb_relation_*` — векторы связей

### Проверить сущности

```bash
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT entity_type, COUNT(*) FROM lightrag_vdb_entity_deepvk_user_bge_m3_1024d GROUP BY entity_type LIMIT 10;"
```

### Проверить AGE граф

```bash
# Метаданные графа
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT name FROM ag_graph;"
```

## Частые вопросы

### Сколько времени занимает создание графа?

Зависит от количества документов и скорости LLM. Entity extraction требует 1 LLM-вызов на чанк (~5-10 секунд на чанк с qwen3.6:35b).

### Как обновить граф после добавления новых документов?

```bash
# Добавить конкретный URL
docker compose exec qa-service uv run python scripts/fill_kb_unified.py \
  --url "https://example.ru/new-doc"
```

Новые документы будут добавлены, существующие пропущены (дедупликация).

## Troubleshooting

### Ошибка "AGE extension not found"

```bash
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT * FROM pg_extension WHERE extname = 'age';"
```

### Пустой граф

```bash
# Проверить логи на ошибки LLM
docker compose logs qa-service | grep -i "error"
# Проверить доступность Ollama
curl -s http://iv-fc.orienteer.ru:12434/api/tags
```

### Ollama "returned empty content"

Модель qwen3.6:35b использует thinking mode. Провайдер автоматически передаёт `think=false` через нативный `/api/chat` endpoint. Если ошибка повторяется — проверить, что сервер Ollama доступен.
