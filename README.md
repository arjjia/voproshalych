# Виртуальный помощник студента ТюмГУ, чат-бот «Вопрошалыч»

Полное название проекта: Виртуальный помощник студента Тюменского государственного университета с агентной архитектурой и динамическим доступом к цифровым ресурсам ТюмГУ.

Система представляет собой многоканальный интеллектуальный сервис поддержки обучающихся ТюмГУ, который обрабатывает обращения студентов, извлекает сведения из официальных цифровых ресурсов университета и формирует ответы на естественном языке.

Заказчик: ФГАОУ ВО «Тюменский государственный университет», управление по сопровождению студентов «Единый деканат».

Исполнители: Ефимова Мария Александровна, Горохов Константин Алексеевич, Батыев Рамиль Рустамович, Мустаков Максим Рашитович.

## Функциональные требования

1. Система должна принимать и обрабатывать сообщения пользователей в каналах VK, Telegram и MAX.
2. Система должна выполнять поиск релевантной информации в официальных цифровых ресурсах ТюмГУ, включая Confluence, sveden.utmn.ru и utmn.ru.
3. Система должна формировать осмысленный ответ на русском языке с использованием LLM и добавлять ссылки на источники в тех случаях, когда ответ опирается на базу знаний.
4. Система должна сохранять в PostgreSQL данные о пользователях, сообщениях и истории вопрос-ответ для последующей аналитики и контроля качества.

## Архитектура

### Компоненты системы

1. **postgres** — PostgreSQL 18 с расширениями pgvector (векторный поиск) и Apache AGE (графовый движок)
2. **db-migrate** — миграции Alembic
3. **qa-service** — Retrieval + Generation, LLM Pool, База Знаний, LightRAG
4. **bot-core** — бизнес-логика диалогов
5. **telegram-bot**, **vk-bot**, **max-bot** — адаптеры платформ

### Tech Stack

| Компонент | Технология |
|-----------|-------------|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 18 + pgvector + Apache AGE |
| Embeddings | deepvk/USER-bge-m3 (1024-dim) |
| LLM Pool | Mistral → GigaChat → OpenRouter |
| RAG | LightRAG (Hybrid Search + Knowledge Graph) |
| Bot Frameworks | aiogram (Telegram), vkbottle (VK), aiohttp (MAX) |

### Схема взаимодействия

```
Пользователь → Telegram/VK/MAX
     ↓
Bot-адаптер → bot-core (8000)
     ↓
QA-service (8004): LightRAG (primary) → Classic RAG (fallback)
     ↓
PostgreSQL (pgvector + AGE)
```

## Быстрый запуск

1. Копирование переменных окружения:
```bash
cp .env.example .env
```

2. Запуск всех сервисов:
```bash
docker compose up -d --build
```

3. Проверка состояния:
```bash
docker compose ps
```

## Конфигурация LightRAG

Основные переменные в `.env`:

```bash
# LightRAG включен
USE_LIGHT_RAG=true

# Хранилище
LIGHT_RAG_STORAGE_TYPE=PostgreSQL
LIGHT_RAG_POSTGRES_URI=postgresql://voproshalych:voproshalych@postgres:5432/voproshalych

# Модель эмбеддингов
LIGHT_RAG_MODEL_NAME=deepvk-user-bge-m3

# Использовать PostgreSQL для графа (требует Apache AGE)
LIGHT_RAG_USE_PG_GRAPH=true
```

## API Endpoints

### QA

| Endpoint | Описание |
|----------|----------|
| `POST /qa` | Основной endpoint с LightRAG + fallback на classic RAG |
| `POST /qa/lightrag` | Только LightRAG |
| `POST /qa/classic` | Только Classic RAG |

### База Знаний

| Endpoint | Описание |
|----------|----------|
| `POST /kb/documents` | Добавить документ в базу знаний |
| `POST /kb/import-to-lightrag` | Импортировать чанки в LightRAG + создать граф |
| `POST /kb/rebuild-knowledge-graph` | Перестроить граф знаний |
| `GET /kb/index-status` | Статус текущего индекса |
| `GET /kb/index-versions` | История версий индекса |
| `GET /kb/chunks/count` | Количество чанков |

### Health

| Endpoint | Описание |
|----------|----------|
| `GET /health` | Health check всех сервисов |

## Тестирование QA-сервиса

### Тестирование LightRAG

```bash
# 1. Проверить статус сервисов
docker compose ps

# 2. Health check
curl http://localhost:8004/health

# 3. Проверить расширения PostgreSQL
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT * FROM pg_extension WHERE extname IN ('vector', 'age');"

# 4. Тест LightRAG (mix mode с fallback)
curl -X POST http://localhost:8004/qa \
  -H "Content-Type: application/json" \
  -d '{"question":"Какие правила приема в магистратуру?"}'

# 5. Тест только LightRAG (без fallback)
curl -X POST http://localhost:8004/qa/lightrag \
  -H "Content-Type: application/json" \
  -d '{"question":"Какие специальности есть в ТюмГУ?"}'

# 6. Проверить статус индекса
curl http://localhost:8004/kb/index-status

# 7. Проверить количество чанков
curl http://localhost:8004/kb/chunks/count

# 8. История версий индекса
curl http://localhost:8004/kb/index-versions
```

### Тестирование Classic RAG

```bash
# Тест только Classic RAG (без LightRAG)
curl -X POST http://localhost:8004/qa/classic \
  -H "Content-Type: application/json" \
  -d '{"question":"Как получить справку об обучении?"}'

# Проверить количество чанков в БД
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT source_type, COUNT(*) FROM chunks GROUP BY source_type;"
```

### Импорт чанков в LightRAG и построение графа знаний

```bash
# 1. Импорт чанков в LightRAG (включает KG extraction)
curl -X POST http://localhost:8004/kb/import-to-lightrag

# 2. Проверить статус импорта
curl http://localhost:8004/kb/index-status

# 3. Ручное построение графа знаний (только KG, без переиндексации)
curl -X POST http://localhost:8004/kb/rebuild-knowledge-graph

# 4. Проверить количество сущностей в VDB
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT COUNT(*) FROM lightrag_vdb_entity_deepvk_user_bge_m3_1024d;"

# 5. Проверить количество связей в VDB
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT COUNT(*) FROM lightrag_vdb_relation_deepvk_user_bge_m3_1024d;"

# 6. Проверить полные сущности KG (извлечённые из документов)
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT COUNT(*) FROM lightrag_full_entities;"

# 7. Проверить полные связи KG
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c \
  "SELECT COUNT(*) FROM lightrag_full_relations;"
```

### Очистка данных LightRAG

```bash
# Удалить все данные LightRAG (при необходимости пересоздать с нуля)
docker compose exec -T postgres psql -U voproshalych -d voproshalych -c "
  TRUNCATE lightrag_doc_chunks, lightrag_doc_full, lightrag_doc_registry, 
           lightrag_doc_status, lightrag_entity_chunks, lightrag_full_entities, 
           lightrag_full_relations, lightrag_index_versions, lightrag_llm_cache, 
           lightrag_relation_chunks, lightrag_vdb_chunks_deepvk_user_bge_m3_1024d,
           lightrag_vdb_entity_deepvk_user_bge_m3_1024d, 
           lightrag_vdb_relation_deepvk_user_bge_m3_1024d 
  RESTART IDENTITY CASCADE;
"
```

### Тестирование fallback логики

```bash
# Основной /qa endpoint автоматически использует fallback
# При LightRAG ошибке → Classic RAG
# Логи можно посмотреть:
docker compose logs qa-service | grep -i "fallback"
```

### Таблицы PostgreSQL

#### Основные таблицы приложения

| Таблица | Описание |
|---------|----------|
| `users` | Пользователи бота |
| `sessions` | Сессии пользователей |
| `messages` | Сообщения пользователей |
| `questions_answers` | История вопросов-ответов |
| `subscriptions` | Подписки пользователей |
| `holidays` | Праздники для рассылок |
| `telemetry_logs` | Логи телеметрии |
| `agent_traces` | Трассировка агентов |
| `alembic_version` | Версии миграций БД |

#### База знаний (chunks)

| Таблица | Описание |
|---------|----------|
| `chunks` | Чанки документов |
| `embeddings` | Эмбеддинги чанков |

#### LightRAG

| Таблица | Описание |
|---------|----------|
| `lightrag_vdb_chunks_*` | Документы в векторном хранилище |
| `lightrag_vdb_entity_*` | Сущности графа знаний |
| `lightrag_vdb_relation_*` | Связи графа знаний |
| `lightrag_full_entities` | Полные извлечённые сущности |
| `lightrag_full_relations` | Полные извлечённые связи |
| `lightrag_doc_registry` | Реестр документов |
| `lightrag_doc_chunks` | Чанки документов |
| `lightrag_doc_full` | Полные документы |
| `lightrag_index_versions` | Версии индекса |
| `lightrag_llm_cache` | Кэш LLM ответов |

#### Расширения PostgreSQL

| Расширение | Описание |
|------------|----------|
| `vector` | Векторный поиск (pgvector) |
| `age` | Графовый движок (Apache AGE) |
| `plpgsql` | Процедурный язык |
| `uuid-ossp` | Генератор UUID |
| `pg_trgm` | Trigram поиск |
| `fuzzystrmatch` | Нечёткий поиск |
| `unaccent` | Удаление акцентов |

## Документация

- `docs/pipeline-user-query.md` — Пайплайн обработки запроса
- `docs/onboarding_guide.md` — Гайд онбординга
- `qa-service/docs/KB_FILL_GUIDE.md` — Заполнение базы знаний
- `qa-service/docs/testing.md` — Тестирование
- `qa-service/docs/knowledge_graph_guide.md` — Создание графа знаний
- `qa-service/docs/message-flow.md` — Поток сообщений
