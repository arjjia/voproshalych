# Onboarding Guide

## Назначение

Этот документ нужен для быстрого входа новых разработчиков в проект `voproshalych`.

## Минимальные шаги перед началом работы

1. Перейдите в корень проекта `voproshalych`.
2. Создайте `.env` из шаблона:

```bash
cp .env.example .env
```

## Шаг 1: Настройка переменных окружения

1. Откройте файл `.env` и заполните обязательные значения.
2. Минимально необходимые переменные:

- `TELEGRAM_BOT_TOKEN`:
  1. Откройте Telegram и найдите `@BotFather`.
  2. Создайте бота командой `/newbot`.
  3. Скопируйте токен и вставьте в `.env`.

- `VK_BOT_TOKEN`:
  1. Создайте или откройте сообщество VK.
  2. Включите сообщения сообщества.
  3. Включите Long Poll API для бота.
  4. Создайте ключ доступа сообщества и вставьте в `.env`.

- `OPENROUTER_API_KEY`:
  1. Зайдите на `openrouter.ai`.
  2. Создайте API key.
  3. Вставьте ключ в `.env`.

- `MISTRAL_API_KEY`:
  1. Зайдите на `mistral.ai`.
  2. Откройте `Try AI Studio -> API Keys`.
  3. Создайте ключ и вставьте в `.env`.

- `GIGACHAT_CLIENT_ID` и `GIGACHAT_CLIENT_SECRET`:
  1. Получите доступ у ответственных за интеграцию GigaChat.
  2. Заполните оба значения в `.env`.

- `CONFLUENCE_TOKEN`:
  1. Запросите токен у администраторов проекта.
  2. Убедитесь, что доступ к нужному пространству Confluence открыт.

3. Опциональные переменные:

- `MAX_BOT_TOKEN`: заполняется только если тестируется MAX-бот.
- `HF_TOKEN`: нужен для более быстрой загрузки embedding-модели при сборке.

4. Базовые переменные БД (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) можно оставить значениями из шаблона для локальной разработки.

## Шаг 2: Запуск сервисов с нуля + импорт дампа БД

Если у вас есть дамп базы данных (например, `dump/voproshalych_20260419_174256.dump`), следуйте этой процедуре для полного поднятия проекта.

### 2.1. Остановить всё и удалить старые данные

```bash
docker compose down -v
```

Это остановит все контейнеры и удалит Docker-том с базой данных. Старые данные будут полностью очищены.

### 2.2. Запустить ТОЛЬКО PostgreSQL

```bash
docker compose up -d postgres
```

Дождитесь статуса `healthy`:

```bash
docker compose ps
# postgres должен показать "(healthy)"
```

### 2.3. Импортировать дамп

Для дампа в custom format (`.dump`, создан через `pg_dump -Fc`):

```bash
docker compose exec -T postgres pg_restore \
  -U voproshalych \
  -d voproshalych \
  --no-owner \
  --no-privileges \
  --clean --if-exists \
  < dump/voproshalych_20260419_174256.dump
```

> **Важно:** Флаг `--no-owner --no-privileges` нужен чтобы не было ошибок с правами.
> Флаг `--clean --if-exists` безопасно удаляет существующие объекты перед восстановлением.

Для дампа в SQL format (`.sql`, создан через `pg_dump` без `-Fc`):

```bash
docker compose exec -T postgres psql -U voproshalych -d voproshalych < dump/voproshalych_YYYYMMDD.sql
```

Если при импорте SQL-дампа возникают ошибки "multiple primary keys" или "already exists":

```bash
docker compose exec -T postgres psql -U voproshalych -d voproshalych \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker compose exec -T postgres psql -U voproshalych -d voproshalych < dump/voproshalych_YYYYMMDD.sql
```

### 2.4. Запустить миграции (пропустить уже применённые)

Alembic автоматически определит, какие миграции уже применены, и выполнит только недостающие:

```bash
docker compose up -d db-migrate
docker compose logs db-migrate --tail 10
# Должно показать "Running upgrade N -> N+1" только для новых миграций
# или ничего, если все миграции уже в дампе
```

### 2.5. Запустить остальные сервисы

```bash
docker compose up -d --build qa-service bot-core telegram-bot vk-bot
```

- Полный запуск (с MAX-ботом):

```bash
docker compose up -d --build
```

### 2.6. Проверить работоспособность

```bash
# Статус всех сервисов
docker compose ps

# qa-service health
curl http://localhost:8004/health

# Тестовый запрос к QA
curl -X POST http://localhost:8004/qa \
  -H "Content-Type: application/json" \
  -d '{"question":"Какие правила приема в магистратуру?"}'
```

## Экспорт дампа (бэкап)

### Custom format (рекомендуется, для `pg_restore`)

```bash
docker compose exec -T postgres pg_dump \
  -U voproshalych \
  -d voproshalych \
  -Fc \
  > dump/voproshalych_$(date +%Y%m%d_%H%M%S).dump
```

### SQL format (для `psql`)

```bash
docker compose exec -T postgres pg_dump \
  -U voproshalych \
  -d voproshalych \
  --clean \
  > dump/voproshalych_$(date +%Y%m%d).sql
```

Экспорт можно делать **без остановки сервисов** — PostgreSQL MVCC гарантирует согласованность дампа.
