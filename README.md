# Виртуальный помощник студента ТюмГУ, чат-бот «Вопрошалыч»

Полное название проекта: Виртуальный помощник студента Тюменского государственного университета с агентной архитектурой и динамическим доступом к цифровым ресурсам ТюмГУ.

Система представляет собой многоканальный интеллектуальный сервис поддержки обучающихся ТюмГУ, который обрабатывает обращения студентов, извлекает сведения из официальных цифровых ресурсов университета и формирует ответы на естественном языке.

Заказчик: ФГАОУ ВО «Тюменский государственный университет», управление по сопровождению студентов «Единый деканат».

Исполнители: Ефимова Мария Александровна, Горохов Константин Алексеевич, Батыев Рамиль Рустамович, Мустаков Максим Рашитович.

## Быстрый запуск

### Системные требования

| Параметр | Минимум |
|----------|---------|
| CPU | 4 ядра |
| RAM | 8 GB |
| Disk | 30 GB |
| OS | Linux (Docker) |
| Docker | 24+ |
| Docker Compose | 2.20+ |

### Установка

```bash
# 1. Скопировать переменные окружения
cp .env.example .env
# Отредактировать .env: заполнить API-ключи, токены ботов, URL Ollama

# 2. Запустить все сервисы
docker compose up -d --build

# Или без MAX-бота и админки:
docker compose up -d --build postgres db-migrate qa-service bot-core telegram-bot vk-bot

# 3. Проверить состояние
docker compose ps
```

### Переменные окружения

Полный список переменных — в [.env.example](.env.example). Основные группы:

| Группа | Переменные | Описание |
|--------|-----------|----------|
| Bot Core | `BOT_CORE_URL`, `TELEGRAM_BOT_TOKEN`, `VK_BOT_TOKEN`, `MAX_BOT_TOKEN` | URL бизнес-логики и токены мессенджеров |
| Database | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` | Подключение к PostgreSQL |
| LLM Providers | `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`, `GIGACHAT_CLIENT_ID` | API-ключи LLM-провайдеров |
| QA Service | `QA_SERVICE_URL`, `DIALOG_CONTEXT_LIMIT_MESSAGES` | Настройки QA-сервиса |
| LightRAG | `LIGHT_RAG_LLM_MODEL`, `LIGHT_RAG_POSTGRES_URI`, `CHUNK_TOKEN_SIZE` | Параметры RAG-движка |
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | LLM для индексации графа знаний |

## Архитектура

### Компоненты системы

| Компонент | Порт | Описание |
|-----------|------|----------|
| **postgres** | 5433 (→5432) | PostgreSQL 18 + pgvector + Apache AGE |
| **db-migrate** | — | Миграции Alembic (однократный запуск) |
| **qa-service** | 8004 | RAG: LightRAG (Hybrid Search + Knowledge Graph), LLM Pool |
| **bot-core** | 8000 | Бизнес-логика диалогов |
| **telegram-bot** | — | Адаптер Telegram (aiogram) |
| **vk-bot** | — | Адаптер VK (vkbottle) |
| **max-bot** | — | Адаптер MAX (aiohttp) |
| **admin-service** | 8005 | Админ-панель (backend) |
| **admin-ui** | 8080 | Админ-панель (frontend) |

### Tech Stack

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3.12, FastAPI |
| Database | PostgreSQL 18 + pgvector + Apache AGE |
| Embeddings | deepvk/USER-bge-m3 (1024-dim) |
| LLM Pool (ответы) | OpenRouter → Mistral → GigaChat |
| LLM (индексация KG) | Qwen 3.6:35b через Ollama (удалённый сервер) |
| RAG | LightRAG v1.4.13 (Hybrid Search + Knowledge Graph) |
| Package Manager | uv |
| Bot Frameworks | aiogram (Telegram), vkbottle (VK), aiohttp (MAX) |

### LightRAG: двухуровневое хранение

LightRAG хранит данные о сущностях и связях одновременно в двух хранилищах:

**SQL таблицы** (pgvector) — векторный поиск по cosine similarity:
- `LIGHTRAG_VDB_CHUNKS_*` — векторы чанков документов
- `LIGHTRAG_VDB_ENTITY_*` — векторы сущностей
- `LIGHTRAG_VDB_RELATION_*` — векторы связей

**AGE граф** (Apache AGE) — графовый обход для цепочек связей:
- `chunk_entity_relation.base` — вершины (сущности)
- `chunk_entity_relation.DIRECTED` — рёбра (связи)

Векторный поиск находит "похожие" сущности, а графовый обход находит "связанные". Пример: запрос "как получить справку-вызов" → векторы находят сущность "Справка-вызов" → графовый обход находит цепочку: `Справка-вызов → Единый личный кабинет → elk.utmn.ru`.

## Заполнение Базы Знаний

Подробная документация: [qa-service/docs/KB_FILL_GUIDE.md](qa-service/docs/KB_FILL_GUIDE.md)

### Источники данных

| Ключ | Источник | Тип документов | Парсер |
|------|----------|----------------|--------|
| `confluence_help` | Confluence (пространство help) | 6 HTML-страниц + дочерние + 2 PDF (OCR) | ConfluenceHelpParser |
| `confluence_study` | Confluence (пространство study) | Все leaf-страницы + PDF вложения (OCR) | ConfluenceStudyParser |
| `sveden` | sveden.utmn.ru | 35 PDF (OCR) + 3 HTML с таблицами | SvedenParser |
| `utmn` | utmn.ru | 1 PDF на 23 страницы (OCR) | UtmnParser |

## Таблицы PostgreSQL

### Основные таблицы приложения

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

### LightRAG

| Таблица | Описание |
|---------|----------|
| `lightrag_doc_full` | Полные документы |
| `lightrag_doc_chunks` | Чанки документов |
| `lightrag_doc_status` | Статус обработки документов |
| `lightrag_full_entities` | Полные данные сущностей |
| `lightrag_full_relations` | Полные данные связей |
| `lightrag_entity_chunks` | Привязка сущностей к чанкам |
| `lightrag_relation_chunks` | Привязка связей к чанкам |
| `lightrag_vdb_chunks_*` | Векторы чанков (pgvector) |
| `lightrag_vdb_entity_*` | Векторы сущностей (pgvector) |
| `lightrag_vdb_relation_*` | Векторы связей (pgvector) |
| `lightrag_llm_cache` | Кэш LLM ответов (для переиспользования) |

### Apache AGE (граф знаний)

| Таблица | Описание |
|---------|----------|
| `ag_graph` | Реестр графов (метаданные) |
| `ag_label` | Типы вершин/рёбер (base, DIRECTED) |
| `chunk_entity_relation.base` | Вершины (сущности) |
| `chunk_entity_relation.DIRECTED` | Рёбра (связи) |

### Расширения PostgreSQL

| Расширение | Описание |
|------------|----------|
| `vector` | Векторный поиск (pgvector) |
| `age` | Графовый движок (Apache AGE) |

## Документация

- `qa-service/docs/KB_FILL_GUIDE.md` — Заполнение базы знаний (подробно)
- `qa-service/docs/INCREMENTAL_INDEX.md` — Справочник документов для инкрементальной индексации
- `qa-service/docs/testing.md` — Тестирование
- `qa-service/docs/knowledge_graph_guide.md` — Создание графа знаний