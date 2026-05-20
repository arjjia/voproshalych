# Виртуальный помощник студента ТюмГУ, чат-бот «Вопрошалыч»

Полное название проекта: Виртуальный помощник студента Тюменского государственного университета с агентной архитектурой и динамическим доступом к цифровым ресурсам ТюмГУ.

Система представляет собой многоканальный интеллектуальный сервис поддержки обучающихся ТюмГУ, который обрабатывает обращения студентов, извлекает сведения из официальных цифровых ресурсов университета и формирует ответы на естественном языке.

Заказчик: ФГАОУ ВО «Тюменский государственный университет», управление по сопровождению студентов «Единый деканат».

Исполнители: Ефимова Мария Александровна, Горохов Константин Алексеевич, Батыев Рамиль Рустамович, Мустаков Максим Рашитович.

## Быстрый запуск

### Установка

```bash
# 1. Скопировать переменные окружения
cp .env.example .env
# Отредактировать .env: заполнить API-ключи, токены ботов, URL Ollama

# 2. Запустить все сервисы
docker compose up -d --build

# Или без MAX-бота и админки:
docker compose up -d --build postgres db-migrate qa-service bot-core vk-bot

# 3. Проверить состояние
docker compose ps
```

### Первый запуск с дампом БД

Если нужно поднять сервисы с нуля и загрузить существующий дамп БД
(например, при развёртывании на новом сервере):

> **Проблема:** после `pg_restore` OID графа Apache AGE ломается —
> схемы получают новые OID, а `ag_graph` хранит старые.
> Скрипт `scripts/fix_age_oid.sh` автоматически чинит все расхождения.

```bash
# 0. Скопировать дамп и скрипт фикса OID в директорию проекта
cp /path/to/your/dump.dump ./dump.dump
cp scripts/fix_age_oid.sh ./fix_age_oid.sh

# 1. Запустить только postgres и дождаться готовности
docker compose up -d postgres
docker compose ps postgres  # должен быть healthy

# 2. Загрузить дамп (очистит существующие данные)
docker compose exec -T postgres pg_restore \
  -U voproshalych -d voproshalych \
  --no-owner --no-privileges --clean --if-exists \
  < dump.dump

# 3. Починить AGE OID (автоматически)
docker compose exec -T postgres bash < fix_age_oid.sh

# 4. Запустить остальные сервисы
docker compose up -d

# 5. Проверить, что AGE граф работает
docker compose exec postgres psql -U voproshalych -d voproshalych -c "
  LOAD 'age';
  SET search_path = ag_catalog, public;
  SELECT count(*) FROM cypher('chunk_entity_relation',
    \$\$MATCH (n) RETURN n\$\$) AS (n agtype);
"
```

### Переменные окружения

Полный список переменных — в [.env.example](.env.example). Основные группы:

### Системные требования

| Параметр | Минимум |
|----------|---------|
| CPU | 4 ядра |
| RAM | 8 GB |
| Disk | 30 GB |
| Docker | 24+ |
| Docker Compose | 2.20+ |

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

## Документация

- `qa-service/docs/KB_FILL_GUIDE.md` — Заполнение базы знаний (подробно)
- `qa-service/docs/INCREMENTAL_INDEX.md` — Справочник документов для инкрементальной индексации
- `qa-service/docs/testing.md` — Тестирование
- `qa-service/docs/knowledge_graph_guide.md` — Создание графа знаний