# Заполнение Базы Знаний

**Статус:** Актуальная версия с поддержкой LightRAG.

## Источники данных

| Источник | Описание | Требует VPN |
|----------|---------|-------------|
| `confluence_study` | Пространство Study на Confluence | ✅ Да |
| `confluence` | Страницы Confluence (политики, положения) | ✅ Да |
| `utmn` | PDF с сайта utmn.ru | ❌ Нет |
| `sveden` | Сведения об организации (sveden.ru) | ❌ Нет |

## Быстрый старт

### 1. Пересборка сервиса

```bash
cd Submodules/voproshalych_v2
docker compose build qa-service
docker compose up -d qa-service
```

### 2. Запуск наполнения

#### Все источники (полная переиндексация)
```bash
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --clear
```

#### Конкретный источник

```bash
# Только Confluence Study
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --clear --source confluence_study

# Только Confluence (политики)
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --clear --source confluence

# Только UTMN
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --clear --source utmn

# Только Sveden
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --clear --source sveden
```

## Режимы запуска

| Параметр | Описание |
|-----------|----------|
| `--clear` | Очистить таблицы и переиндексировать с нуля |
| `--resume` | Инкрементальная индексация (пропускает уже обработанные) |
| `--append` | Добавить без проверки дубликатов |

### Примеры использования

```bash
# Очистка и полная переиндексация confluence_study
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --clear --source confluence_study

# Добавить новые документы к существующим (инкрементально)
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --resume --source confluence_study

# Добавить документы без проверки (может создать дубликаты)
docker exec -i voproshalych_v2-qa-service-1 uv run python scripts/fill_kb_from_sources.py --append --source confluence_study
```

## Мониторинг

### Проверить количество чанков
```bash
docker exec voproshalych_v2-postgres-1 psql -U voproshalych -d voproshalych -c "SELECT source_type, COUNT(*) FROM chunks GROUP BY source_type;"
```

### Проверить текст в чанках
```bash
docker exec voproshalych_v2-postgres-1 psql -U voproshalych -d voproshalych -c "SELECT title, LENGTH(text) as len FROM chunks ORDER BY len DESC LIMIT 10;"
```

### Логи процесса
```bash
# Смотреть логи контейнера
docker logs voproshalych_v2-qa-service-1 --tail 50
```

## Конфигурация OCR (.env)

```bash
# Параллельные потоки для OCR (по умолчанию 4)
OCR_WORKERS=4

# Разрешение для OCR: 150-300 DPI (меньше = быстрее, больше = качественнее)
OCR_RESOLUTION=150

# Размер чанка в токенах для LightRAG
CHUNK_TOKEN_SIZE=1024

# Перекрытие чанков в токенах
CHUNK_OVERLAP_TOKEN_SIZE=200
```

## Как работает парсинг

### Confluence Study
1. Получает все страницы пространства Study
2. Для каждой страницы:
   - Извлекает HTML текст (если >100 символов)
   - Скачивает PDF вложения
   - Запускает OCR для каждого PDF (параллельно, max 2 одновременно)
3. Сохраняет чанки в PostgreSQL
4. Импортирует в LightRAG

### PDF парсинг
- Использует Tesseract OCR с языками `rus+eng`
- Параллельная обработка PDF (semaphore = 2)
- Native text extraction + OCR fallback

### LightRAG
- Чанкинг: 1024 токена, перекрытие 200 токенов
- Векторное хранилище: PostgreSQL (PGVector)
- Графовое хранилище: PostgreSQL (AGE)

## Остановка процесса

```bash
# Перезапустить контейнер (остановит процесс)
docker compose restart qa-service

# Или убить процесс
docker exec voproshalych_v2-qa-service-1 pkill -f fill_kb_from_sources
```

## Очистка БД вручную

```bash
docker exec voproshalych_v2-postgres-1 psql -U voproshalych -d voproshalych -c "TRUNCATE chunks, embeddings, kb_documents_registry RESTART IDENTITY CASCADE;"
```

## Устранение проблем

### Парсинг зависает на PDF
- Проверьте логи: `docker logs voproshalych_v2-qa-service-1`
- Убедитесь что VPN включён (для Confluence)
- Попробуйте уменьшить `OCR_WORKERS=2` в .env

### Ошибки подключения к Confluence
- Проверьте VPN
- Проверьте `CONFLUENCE_TOKEN` в .env

### Мало чанков после парсинга
- Запустите с `--clear --source <источник>` для полной переиндексации
- Проверьте что страницы не были отфильтрованы (короткий контент)
