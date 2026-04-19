# Заполнение Базы Знаний (LightRAG)

**Статус:** Актуальная версия. Единый скрипт `fill_kb_unified.py` с поддержкой LightRAG, удалённой Ollama, sentence-aware чанкинга и инкрементального режима.

## Содержание

- [Источники данных](#источники-данных)
- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Режимы запуска](#режимы-запуска)
- [Инкрементальный режим](#инкрементальный-режим)
- [Мониторинг](#мониторинг)
- [Конфигурация](#конфигурация)
- [Как работает парсинг](#как-работает-парсинг)
- [Устранение проблем](#устранение-проблем)

## Источники данных

| Источник | Ключ `--source` | Описание | Требует VPN |
|----------|-----------------|----------|-------------|
| Confluence Help | `confluence_help` | Пространство help (HTML + 2 PDF) | ✅ Да |
| Confluence Study | `confluence_study` | Пространство study (HTML + PDF) | ✅ Да |
| Sveden | `sveden` | PDF с sveden.utmn.ru (whitelist 35 URL) + 3 HTML с таблицами | ❌ Нет |
| UTMN | `utmn` | PDF с сайта utmn.ru | ❌ Нет |

## Требования

### 1. Ollama (LLM для индексации)

Для построения графа знаний LightRAG использует LLM. Используется **удалённая Ollama** с моделью `qwen3.6:35b` на сервере `iv-fc.orienteer.ru:12434`.

**Проверить что удалённая Ollama отвечает:**

```bash
curl -s http://iv-fc.orienteer.ru:12434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3.6:35b", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}' \
  | python3 -m json.tool
```

> **Примечание:** Модель работает на удалённом сервере, локальная Ollama не требуется. Доступ к серверу должен быть открыт по сети.

### 2. VPN (для Confluence)

Для источников `confluence_help` и `confluence_study` нужен корпоративный VPN.

### 3. Переменные окружения (.env)

```bash
# LLM для LightRAG (ollama = удалённая модель qwen3.6:35b)
LIGHT_RAG_LLM_MODEL=ollama
OLLAMA_BASE_URL=http://iv-fc.orienteer.ru:12434
OLLAMA_MODEL=qwen3.6:35b

# Чанкинг (sentence-aware)
CHUNK_TOKEN_SIZE=500
CHUNK_OVERLAP_TOKEN_SIZE=50
```

## Быстрый старт

### 1. Пересборка сервиса

```bash
cd Submodules/voproshalych_v2
docker compose build qa-service
docker compose up -d qa-service
```

### 2. Запуск наполнения

#### Все источники без графа (быстро, без LLM)

```bash
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --no-graph
```

#### Все источники с графом через Ollama

```bash
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear
```

#### Конкретный источник

```bash
# Только Confluence Help (нужен VPN)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source confluence_help

# Только Confluence Study (нужен VPN)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source confluence_study

# Только Sveden
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source sveden

# Только UTMN
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source utmn
```

#### С ограничением количества документов (для тестирования)

```bash
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --source sveden --limit 3
```

## Режимы запуска

### Параметры командной строки

| Параметр | Описание |
|-----------|----------|
| `--clear` | Очистить **все** таблицы LightRAG перед индексацией |
| `--no-graph` | Отключить построение графа знаний (не нужны LLM запросы) |
| `--source <ключ>` | Индексировать только выбранный источник |
| `--limit <N>` | Ограничить количество документов |
| `--url <URL>` | Инкрементальный режим: индексировать конкретный URL (можно указать несколько раз) |
| `--force` | С `--url`: переиндексировать документ (удалить старый + вставить новый) |

### Типичные сценарии (массовый режим)

```bash
# Быстрая проверка: 3 документа без графа
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --source sveden --limit 3 --no-graph

# Полная переиндексация всего без графа
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear --no-graph

# Полная переиндексация с графом (нужна Ollama!)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --clear
```

## Инкрементальный режим

Для добавления или переиндексации отдельных документов без полной переиндексации.

### Добавить документ

```bash
# Если документ уже в БД — будет пропущен
docker compose exec qa-service uv run python scripts/fill_kb_unified.py \
  --url "https://sveden.utmn.ru/sveden/files/vie/Prikaz.pdf"

# Несколько документов
docker compose exec qa-service uv run python scripts/fill_kb_unified.py \
  --url "https://sveden.utmn.ru/sveden/managers/" \
  --url "https://sveden.utmn.ru/sveden/files/vie/Prikaz.pdf"
```

### Переиндексировать документ

```bash
# --force удаляет старый документ + чанки из всех таблиц, затем вставляет заново
docker compose exec qa-service uv run python scripts/fill_kb_unified.py \
  --force --url "https://sveden.utmn.ru/sveden/managers/"
```

### Маршрутизация URL

При `--url` скрипт автоматически определяет тип обработки по URL-паттерну:

| URL-паттерн | source_type | Метод |
|-------------|-------------|-------|
| `confluence.utmn.ru` + `pageId=` | `confluence_help` | REST API → HTML |
| `confluence.utmn.ru` + `.pdf` | `confluence_help` | OCR |
| `sveden.utmn.ru/sveden/managers/` | `sveden` | HTML + таблицы |
| `sveden.utmn.ru/sveden/catering/` | `sveden` | HTML + таблицы |
| `sveden.utmn.ru/sveden/struct` | `sveden` | HTML + таблицы |
| `sveden.utmn.ru` + `.pdf` | `sveden` | OCR |
| `utmn.ru` + `.pdf` | `utmn` | OCR |
| Любой `.pdf` | `utmn` | OCR (fallback) |

Полный справочник документов: [INCREMENTAL_INDEX.md](./INCREMENTAL_INDEX.md)

## Мониторинг

### Проверить заполнение таблиц LightRAG

```bash
docker compose exec postgres psql -U voproshalych -d voproshalych -c "
SELECT table_name,
       (xpath('/row/cnt/text()', query_to_xml(format('SELECT count(*) AS cnt FROM %I', table_name), false, true, '')))[1]::text::int AS rows
FROM (
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name LIKE 'lightrag_%'
) t ORDER BY table_name;"
```

### Проверить содержимое чанков

```bash
docker compose exec postgres psql -U voproshalych -d voproshalych -c "
SELECT LEFT(content, 100) as preview, tokens, full_doc_id
FROM lightrag_vdb_chunks_deepvk_user_bge_m3_1024d
ORDER BY create_time DESC LIMIT 10;"
```

### Логи процесса

```bash
# Логи контейнера
docker logs voproshalych_v2-qa-service-1 --tail 50 -f

# Логи Ollama (если есть проблемы)
# Откройте Ollama.app → меню → View Logs
```

## Конфигурация

### Чанкинг (.env)

```bash
# Размер чанка в токенах (500 ≈ 1000-1500 символов русского текста)
CHUNK_TOKEN_SIZE=500

# Перекрытие между чанками в токенах
CHUNK_OVERLAP_TOKEN_SIZE=50

# Разделитель для sentence-aware чанкинга (передаётся в ainsert)
# SPLIT_BY_CHARACTER=". "
```

### OCR (.env)

```bash
# Параллельные потоки для OCR (по умолчанию 4)
OCR_WORKERS=4

# Разрешение для OCR: 150-300 DPI (меньше = быстрее, больше = качественнее)
OCR_RESOLUTION=150
```

## Как работает парсинг

### Общая схема

```
Парсеры → fill_kb_unified.py → LightRAG.ainsert()
                                        ├── Сохранение документа (lightrag_doc_full)
                                        ├── Нарезка на чанки (split_by_character=". ")
                                        │   └── lightrag_doc_chunks + lightrag_vdb_chunks_*
                                        ├── Entity extraction (LLM → Ollama)
                                        │   └── lightrag_full_entities + lightrag_vdb_entity_*
                                        └── Relation extraction (LLM → Ollama)
                                            └── lightrag_full_relations + lightrag_vdb_relation_*
```

### Storage: все данные в PostgreSQL

| Хранилище | Класс | Назначение |
|-----------|-------|------------|
| KV | `PGKVStorage` | Документы, чанки, сущности, связи, LLM-кэш |
| Vector | `PGVectorStorage` | Векторные эмбеддинги (chunks, entity, relation) |
| Graph | `PGGraphStorage` | Граф знаний (Apache AGE) |
| Doc Status | `PGDocStatusStorage` | Статус обработки документов |

### Confluence Help

1. Парсит HTML контент 6 конкретных страниц пространства `help`
2. Для страниц Яндекс 360 и Единый личный кабинет — рекурсивно обходит дочерние
3. PDF вложения со страниц **не парсятся** (ссылки остаются как текст)
4. Отдельно OCR-парсит 2 PDF документа (Условия Wi-Fi, Положение об Интернете)

### Confluence Study

1. Получает все страницы пространства Study через REST API
2. Пропускает страницы с дочерними (только leaf-страницы)
3. Извлекает HTML текст + PDF вложения с OCR

### Чанкинг

- **Sentence-aware**: текст сначала разбивается по `. ` (границы предложений)
- **Токенный лимит**: каждый чанк ≤ 500 токенов (~1000-1500 символов)
- Если предложение длиннее лимита — дополнительно режется по токенам с перекрытием

## Остановка процесса

```bash
# Перезапустить контейнер (остановит процесс)
docker compose restart qa-service

# Или убить процесс внутри контейнера
docker exec voproshalych_v2-qa-service-1 pkill -f fill_kb_unified
```

## Очистка БД вручную

```bash
# Очистить все таблицы LightRAG
docker compose exec postgres psql -U voproshalych -d voproshalych -c "
DO \$\$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name LIKE 'lightrag_%'
    LOOP
        EXECUTE format('TRUNCATE TABLE %I CASCADE', t);
        RAISE NOTICE 'Cleared: %', t;
    END LOOP;
END \$\$;"
```

## Устранение проблем

### Ollama не отвечает из Docker

```bash
# Проверить что Ollama запущена на хосте
curl -s http://localhost:11434/api/tags | python3 -m json.tool

# Проверить доступ из контейнера
docker exec voproshalych_v2-qa-service-1 curl -s http://host.docker.internal:11434/api/tags
```

### Mistral "Server disconnected"

Используйте `--no-graph` для индексации без LLM, или переключитесь на Ollama (`LIGHT_RAG_LLM_MODEL=ollama`).

### Парсинг зависает на PDF

- Проверьте логи: `docker logs voproshalych_v2-qa-service-1`
- Уменьшите `OCR_WORKERS=2` в .env

### Ошибки подключения к Confluence

- Включите корпоративный VPN
- Проверьте `CONFLUENCE_TOKEN` в .env

### Мало чанков после парсинга

- Запустите с `--clear --source <источник>` для полной переиндексации
- Проверьте что страницы не были отфильтрованы (короткий контент < 50 символов)

### Ollama сервер недоступен

```bash
# Проверить доступность удалённого Ollama
curl -s http://iv-fc.orienteer.ru:12434/api/tags

# Если не отвечает — проверить сетевую доступность сервера
ping iv-fc.orienteer.ru
```
