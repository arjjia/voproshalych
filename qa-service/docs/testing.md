# Тестирование QA-сервиса

## Быстрые команды

### Запуск сервиса

```bash
# Через Docker
docker compose up -d qa-service

# Локально с переменными окружения
uv run uvicorn qa.main:app --host 0.0.0.0 --port 8004
```

### Проверка работоспособности

```bash
# Health check
curl http://localhost:8004/health

# Тестовый запрос (LightRAG)
curl -X POST http://localhost:8004/qa \
  -H "Content-Type: application/json" \
  -d '{"question": "Какие правила приёма в ТюмГУ?"}'
```

### Запуск тестов

```bash
# Все тесты
uv run pytest

# Только unit-тесты
uv run pytest tests/unit/

# С покрытием кода
uv run pytest --cov=src --cov-report=html
```

### Docker команды

```bash
docker compose build qa-service
docker compose up -d postgres qa-service
docker compose logs qa-service
docker compose down
```

## Тестирование LightRAG

### Проверка статуса

```bash
curl http://localhost:8004/health

docker compose logs qa-service | grep -i "lightrag"
```

### Проверка графа знаний

```bash
# Расширения PostgreSQL
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT * FROM pg_extension WHERE extname IN ('vector', 'age');"

# Таблицы LightRAG
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "\dt" | grep lightrag

# Количество сущностей и связей
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT 'entities' AS type, COUNT(*) FROM lightrag_full_entities
   UNION ALL SELECT 'relations', COUNT(*) FROM lightrag_full_relations
   UNION ALL SELECT 'chunks', COUNT(*) FROM lightrag_doc_chunks;"
```

### Статистика БЗ

```bash
curl http://localhost:8004/kb/stats
```

### Заполнение БЗ

```bash
# Полная переиндексация
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear

# Один источник
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source sveden

# Инкрементально
docker compose exec qa-service uv run python scripts/fill_kb_unified.py \
  --url "https://sveden.utmn.ru/sveden/managers/"
```

Подробнее: [KB_FILL_GUIDE.md](./KB_FILL_GUIDE.md)

## Структура тестов

### Unit-тесты

- `tests/unit/test_llm_pool.py` — тесты LLM Pool
- `tests/unit/test_providers.py` — тесты провайдеров

### Интеграционные тесты

- `tests/integration/test_qa_api.py` — тесты API
- `tests/integration/test_lightrag.py` — тесты LightRAG

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `MISTRAL_API_KEY` | API ключ Mistral AI | - |
| `OPENROUTER_API_KEY` | API ключ OpenRouter | - |
| `GIGACHAT_CLIENT_ID` | Client ID GigaChat | - |
| `GIGACHAT_CLIENT_SECRET` | Client Secret GigaChat | - |
| `POSTGRES_HOST` | Хост PostgreSQL | `postgres` |
| `POSTGRES_DB` | Имя БД | `voproshalych` |
| `LIGHT_RAG_USE_PG_GRAPH` | Использовать PG для графа | `true` |
| `LIGHT_RAG_LLM_MODEL` | LLM для индексации | `ollama` |
| `OLLAMA_BASE_URL` | URL Ollama сервера | `http://localhost:11434` |
| `OLLAMA_MODEL` | Модель Ollama | `qwen3.6:35b` |
| `CHUNK_TOKEN_SIZE` | Размер чанка (токены) | `500` |
| `CHUNK_OVERLAP_TOKEN_SIZE` | Перекрытие чанков | `50` |

## Частые проблемы

### Ошибка "No available LLM providers"

```bash
echo $OPENROUTER_API_KEY
echo $MISTRAL_API_KEY
```

### Ошибка подключения к PostgreSQL

```bash
docker compose ps
docker compose logs postgres
```

### LightRAG не инициализируется

```bash
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT * FROM pg_extension WHERE extname = 'age';"
docker compose logs qa-service | grep -i error
```
