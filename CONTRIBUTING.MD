# Contributing

Стандарт разработки проекта «Вопрошалыч» — виртуальный помощник студента ТюмГУ.

> Если в репозитории вы обнаружите несоответствие с оглашёнными ниже положениями, создайте issue с указанием строки кода и несоответствия.

## Структура проекта

```
voproshalych_v2/
├── bot-service/        # Бизнес-логика диалогов (FastAPI)
├── qa-service/         # RAG-сервис: LightRAG + LLM Pool (FastAPI)
├── max-bot/            # Адаптер MAX (Go)
├── admin-service/      # Админ-панель backend
├── admin-ui/           # Админ-панель frontend
├── scripts/            # Вспомогательные скрипты
├── docker-compose.yml
└── .env.example
```

## Стандарт оформления кода

### Python

- **PEP 8** — базовый стиль кода
- **Black** — автоформатирование, длина строки 88 символов
- **Google-style docstrings** — документирование функций и классов
- **isort** — сортировка импортов

Пример docstring:

```python
def process_question(question: str, context: str | None = None) -> dict:
    """Обработать вопрос пользователя.

    Args:
        question: Текст вопроса.
        context: История диалога.

    Returns:
        dict: Ответ с ключами answer, model, sources.
    """
```

### Go (max-bot)

- `gofmt` / `goimports`
- Стандартные рекомендации Effective Go

## Git Commits

Формат: Conventional Commits

```
type(scope): description

[optional body]
```

**Типы:**
- `feat` — новая функциональность
- `fix` — исправление бага
- `refactor` — рефакторинг без изменения поведения
- `docs` — документация
- `test` — тесты
- `chore` — сборка, CI, зависимости
- `perf` — оптимизация производительности

**Области (scope):**
- `qa` — qa-service
- `bot` — bot-service
- `max` — max-bot
- `admin` — admin-service / admin-ui

Примеры:
```
feat(qa): add question routing with classification
fix(bot): truncate long Telegram messages
refactor(qa): split LightRAG search and LLM generation
docs: update CONTRIBUTING.MD
```

## Тестирование

### Запуск тестов

```bash
# QA-service
cd qa-service
pytest tests/ -v

# Bot-service
cd bot-service
pytest core/tests/ -v

# С покрытием
pytest tests/ --cov=qa --cov-report=term-missing
```

### Правила тестирования

- Юнит-тесты для бизнес-логики (сервисы, утилиты, парсеры)
- Интеграционные тесты для API endpoints (с моками внешних зависимостей)
- Тесты лежат в `tests/unit/` и `tests/integration/`
- Имена файлов: `test_*.py`
- Фикстуры в `conftest.py`

## Запуск и разработка

```bash
# Скопировать env
cp .env.example .env

# Запустить все сервисы
docker compose up -d --build

# Запустить без MAX-бота и админки
docker compose up -d --build postgres db-migrate qa-service bot-core telegram-bot vk-bot
```

## Code Review

- Каждый Merge Request проходит ревью
- Проверяются: стиль кода, тесты, документация
- MR не принимается с проваленными тестами или ошибками линтера
