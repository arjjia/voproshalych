# MVP GAPS REPORT

> **Цель:** Зафиксировать все расхождения между **текущей реализацией MVP**
> (`Submodules/voproshalych_v2/v3/`) и **целевой MVP-архитектурой**
> (`Voproshalych-v3/V3/MVP_01_FUNCTIONAL_REQUIREMENTS.md`,
> `Voproshalych-v3/V3/MVP_02_ARCHITECTURE.md`).
>
> Дата: 2026-07-14

---

## Статусная сводка

| Метрика | Значение |
|---------|----------|
| Всего сервисов в docker-compose | 12 |
| MCP-серверов в config | **3** ✅ (kb, news, fetch) |
| MCP-серверов по MVP-target | **3** (kb, news, fetch) |
| Источников БЗ в коде | **4** — Confluence Help/Study, News, Events |
| Источников БЗ по MVP-target | **4** — Confluence (help+study) + News + Events |
| Эмбеддинги | ✅ deepvk/USER-bge-m3 (локально) ✅ |
| Auth | ✅ LobeHub server-mode + Better Auth |
| Согласие на ПДн | ⚠ Статическая HTML-страница (localStorage), не в БД |
| Стриминг | ⚠ Псевдо-стриминг (ответ генерируется целиком, потом отдаётся) |
| Daily re-index новостей | ❌ Отсутствует |
| Поле «Интересы» | ❌ Отсутствует |
| Настоящий стриминг токенов LLM | ❌ Отсутствует |

---

## 1. КРИТИЧЕСКИЕ РАСХОЖДЕНИЯ

### 1.1. ✅ Лишние MCP-серверы развёрнуты и доступны агенту

**Файлы:** `docker-compose.yml:143-205`, `agent-service/src/config.py:34-36`,
`agent-service/src/main.py:384-392`, `agent-service/src/nodes/react.py:21-26`

**Что в MVP target:** Только 3 MCP-сервера:
- `mcp-kb` (Confluence help+study)
- `mcp-news` (stories + events, с учётом интересов)
- `mcp-fetch` (live HTTP)

**Статус: 🔧 ИСПРАВЛЕНО (2026-07-14)**

Удалены из docker-compose.yml (3 сервиса: mcp-contacts, mcp-library, mcp-sveden).
Удалены из agent-service config.py (список MCP_URLS теперь 3 записи).
Удалены из react.py (MCP_SERVERS теперь 4: kb, news, events, fetch).
Удалены из main.py `/mcp/tools` (возвращает только 3 сервера).
Связанные парсеры и crawl-инструменты удалены из kb-service (crawl_utmn, crawl_sveden,
crawl_utmn_faq, crawl_utmn_contacts, UtmnParser, SvedenParser, UtmnFaqParser,
UtmnContactsParser).

Все 63 unit-теста проходят.

---

### 1.2. Нет daily re-index новостей/событий

**Файлы:** `kb-service/src/kb/main.py`, `kb-service/src/kb/tools.py:555-602`

**Что в MVP target (§4.2):**
> Ежедневное обновление через очередь/планировщик: добавить новое, пометить
> устаревшие события архивом (по дате).

**Что фактически:** Парсеры `crawl_utmn_news` и `crawl_utmn_events` существуют
и умеют сканировать ленты, но:
- Нет автоматического запуска (нет cron/планировщика/RQ-воркера)
- Нет архивации устаревших событий по дате
- Заполнение БЗ — только ручной вызов через `curl` (см. README.md:220-231)
- Новости падают в ту же таблицу `kb_chunks`, что и Confluence — без выделенного workspace `news_events`

**Исправление:** Добавить сервис scheduler (Redis Queue / cron в kb-service)
с daily pipeline для парсинга новостей, проверки дат и архивации.

---

### 1.3. get_events не принимает interests и date_range

**Файл:** `mcp-servers/src/public/news_server.py:110-140`

**Что в MVP target (§4.2):**
> `get_events(topic, date_range, interests)` — учитывает интересы пользователя.

**Что фактически:**
```python
async def get_events(limit: int = 5) -> str:
```
Параметры: только `limit`. Нет фильтрации по дате, теме, интересам.
Парсинг — через BeautifulSoup с хрупкими селекторами.

**Исправление:** Переработать сигнатуру, добавить фильтрацию по дате,
поддержку интересов пользователя.

---

### 1.4. Нет поля «Интересы» и учёта интересов

**Что в MVP target (§0, решение Марии):**
> Поле **«Интересы»** — **реальное**, учитывается при формировании подборок
> мероприятий по интересам (не заглушка).

**Что фактически:** Никакого поля «Интересы» нет:
- Нет в моделях AgentState/Profile
- Нет в middleware (передаёт только user_id + role)
- Нет в UI LobeHub
- Нет в get_events

**Исправление:** Добавить поле в Profile → AgentState, пробрасывать из LobeHub,
UI-вкладка профиля, передавать в get_events.

---

### 1.5. Согласие на ПДн — не в БД (localStorage)

**Файл:** `lobe-chat/consent.html`

**Что в MVP target (§3.5):**
> При первой регистрации — форма согласия на обработку ПДн (факт + дата → в БД).

**Что фактически:** Consent screen есть (статический HTML), но:
- Согласие хранится только в `localStorage` браузера
- Нет записи в БД (нет таблицы `user_consent`)
- Нет даты согласия
- Факт согласия не привязан к пользователю (только к браузеру)

**Исправление:** Создать таблицу в БД, API-эндпоинт для сохранения согласия,
LobeHub плагин/экран вызывает API.

---

### 1.6. Стриминг — псевдо-стриминг (нет потоковой генерации)

**Файлы:** `agent-service/src/main.py:130-175`, `agent-service/src/streaming.py`

**Что в MVP target:** Настоящий стриминг токенов (первое слово ≤ 1.5с).

**Что фактически:**
```
graph.ainvoke(state)  ← весь граф выполняется синхронно (секунды)
    ↓
stream_agent_events() ← готовый ответ отдаётся как SSE-события
                    (не токены, а целиком за один "token" event)
```

В `_openai_stream_response()` ответ отдаётся **посимвольно**, но это тоже
постфактум — символы уже готового текста, не живые токены LLM.

SSE в `/chat/stream` эмулирует события `thought`/`tool_call`/`token`, но все
они генерируются **после** выполнения графа. Настоящего пошагового стриминга
(каждого шага LangGraph по мере выполнения) нет.

**Исправление:** Использовать `graph.astream_events()` (LangGraph streaming) +
aiter шагов с yield каждого события в реальном времени.

---

### 1.7. hybrid_search — заглушка

**Файл:** `kb-service/src/kb/search.py:48-60`

**Что в MVP target:** Гибридный поиск (векторный + полнотекстовый), опционально реранкер.

**Что фактически:**
```python
async def hybrid_search(...) -> list[dict]:
    return await vector_search(...)  # просто вызывает векторный поиск
```
Полнотекстовый поиск (FTS) не реализован. Нет реранкера.

**Исправление:** Реализовать FTS (pgvector + tsvector), добавить реранкер.

---

## 2. СУЩЕСТВЕННЫЕ РАСХОЖДЕНИЯ

### 2.1. Трассировка в JSONL-файлы, а не в БД

**Файлы:** `agent-service/src/trace_logger.py`

**Что в MVP target (§Ф8):** Трейсинг агентских шагов — хотя бы таблица `agent_traces`.

**Что фактически:** JSONL-файлы в `/tmp/agent-traces/`. Это не масштабируется,
нельзя сделать SQL-запросы по трейсам.

**Файловая трассировка:**
- Пропадает при рестарте контейнера (если не смонтирован volume)
- Нельзя анализировать через SQL
- Нет связи с пользователями

**Исправление:** Перенести в таблицу PostgreSQL (agent_traces).

---

### 2.2. X-User-Id пробрасывается, но не используется

**Файлы:** `agent-service/src/middleware.py`, `agent-service/src/main.py:84-88`

**Что в MVP target (§3.3):**
> В MVP user_id не влияет на доступ к данным (всё публичное), но готовит почву.

**Что фактически:** user_id и role пробрасываются через middleware → Profile →
AgentState, но дальнейшего использования нет. Соответствует MVP target формально,
но:

- Нет изоляции workspace по user_id/role (все в workspace="default"/"public")
- Нет связи между сессией LobeHub и контекстом в agent-service
- Role никак не проверяется и не влияет на маршрутизацию

---

### 2.3. mcp-news использует хрупкий HTML-парсинг

**Файл:** `mcp-servers/src/public/news_server.py:31-73`

Парсинг через BeautifulSoup с жёстко закодированными CSS-селекторами:
```python
article_selectors = [
    "div.news-list__item", "div.news-item", "div.news_card", ...
]
title_selectors = [
    "h2, h3, h4, .news-list__title, .news-item__title, ..."
]
```

При любом изменении вёрстки utmn.ru парсинг сломается.
_RSS fallback есть, но он не всегда доступен._

---

### 2.4. ReAct-агент без structured output / function calling

**Файл:** `agent-service/src/nodes/react.py:49-61`

LLM должна вернуть JSON вида `{"action": "...", ...}` в свободной форме.
Нет Pydantic-валидации, нет OpenAI function calling, нет JSON Schema.

```python
decision = _extract_json(decision)  # убирает markdown-обёртки
data = json.loads(decision)         # может упасть с JSONDecodeError
```

Это делает ReAct нестабильным: LLM может вернуть невалидный JSON,
и агент упадёт. Нет ретраев при ошибке парсинга.

---

### 2.5. Нет отдельного workspace `news_events`

**Файлы:** `kb-service/src/kb/search.py:29`, `kb-service/src/kb/models.py`

**Что в MVP target:** Workspace `news_events` для новостей/событий, отдельный
векторный индекс.

**Что фактически:** Все чанки (Confluence help, Confluence study, новости, события)
падают в один workspace — `"default"`. Нет разделения.

При поиске используется `WHERE c.workspace = :workspace` с параметром
`workspace="public"` (hardcoded в `kb_workflow.py:38`). Это значит, что
поиск не видит ничего, что лежит в другом workspace.

---

### 2.6. Нет rate limiting / защиты эндпоинтов

**Файл:** `agent-service/src/main.py`

Все эндпоинты открыты:
- CORS: `allow_origins=["*"]`
- Нет API-ключей для agent-service
- Нет rate limiting
- Любой может вызвать `/v1/chat/completions`

---

### 2.7. agent_traces не имеют связи с пользователями

Трассы записываются в JSONL с `request_id`, но нет привязки к `user_id`.
Нельзя ответить на вопрос «какие запросы делал пользователь Х».

---

## 3. НЕЗНАЧИТЕЛЬНЫЕ РАСХОЖДЕНИЯ / ЗАМЕЧАНИЯ

### 3.1. model_priority дублируется

**Файлы:** `agent-service/src/config.py:16-30`, `kb-service/src/kb/config.py:23-37`

Один и тот же список из 13 моделей. Если менять — надо в обоих местах.
Нужен единый источник конфигурации.

### 3.2. Стриминг `/chat/stream` не использует dialog_context

В отличие от POST `/chat`, SSE-эндпоинт не принимает `dialog_context` —
каждый запрос идёт без истории.

### 3.3. Нет Alembic миграций для таблиц agent-service

Миграции есть только для kb-service (создание таблиц через `create_all`).
Нет миграций для `agent_traces`, `user_consent` и т.д.

### 3.4. LobeHub не пробрасывает X-User-Id

В `docker-compose.yml:243` проброса `X-User-Id` нет. middleware получает
всегда `"anonymous"`.

### 3.5. Нет вкладки «Цифровой профиль» в LobeHub

По MVP target не требуется (post-MVP), но поле «Интересы» — требуется
(см. 1.4). LobeHub не имеет кастомной вкладки.

---

## 4. ДИАГРАММА РАСХОЖДЕНИЙ (ТЕКСТОВАЯ)

```
MVP TARGET                                 ТЕКУЩАЯ РЕАЛИЗАЦИЯ
═══════════                                ═════════════════════

MCP-серверы:                               MCP-серверы (ИСПРАВЛЕНО):
  mcp-kb ✅    mcp-news ✅  mcp-fetch ✅      mcp-kb ✅    mcp-news ✅  mcp-fetch ✅
  mcp-contacts ❌ (вне MVP)                  mcp-contacts ❌ УДАЛЁН
  mcp-library  ❌ (вне MVP)                  mcp-library  ❌ УДАЛЁН
  mcp-sveden   ❌ (вне MVP)                  mcp-sveden   ❌ УДАЛЁН

Источники БЗ:                              Источники БЗ (ИСПРАВЛЕНО):
  Confluence (help+study) ✅                 Confluence (help+study) ✅
  News (stories)        ✅                   News (stories)        ✅
  Events                ✅                   Events                ✅
  ❌ utmn.ru общий      ❌                   ❌ utmn.ru общий      ❌ УДАЛЁН
  ❌ sveden             ❌                   ❌ sveden              ❌ УДАЛЁН
  ❌ FAQ                ❌                   ❌ FAQ                 ❌ УДАЛЁН
  ❌ Контакты           ❌                   ❌ Контакты            ❌ УДАЛЁН

Workspace:
  news_events — отдельный                    Все в одном workspace "default"
  public — Confluence

Пайплайн новостей:                          Пайплайн новостей:
  Daily re-index + архивация                  Ручной crawl (curl)
  Queue/Scheduler                             Нет автоматизации

get_events:
  get_events(topic, date_range, interests)   get_events(limit)

Согласие ПДн:
  В БД (факт + дата)                         localStorage (браузер)

Эмбеддинги:
  deepvk/USER-bge-m3 (локально) ✅            deepvk/USER-bge-m3 (локально) ✅

Стриминг:
  Настоящий стриминг токенов                   Псевдо-стриминг
  (пошаговый через astream_events)             (graph.ainvoke → готовый ответ)

hybrid_search:
  Векторный + полнотекстовый                   Только векторный (заглушка)
```

---

## 5. ПРИОРИТЕТЫ ИСПРАВЛЕНИЙ

| # | Расхождение | Приоритет | Усилия | Статус |
|---|-------------|-----------|--------|--------|
| 1 | Убрать лишние MCP из docker-compose | 🔴 High | 15 мин | ✅ |
| 2 | Убрать contacts/library/sveden из react.py/config | 🔴 High | 15 мин | ✅ |
| 3 | Daily re-index news/events | 🔴 High | 2-3 дня | ⏳ |
| 4 | get_events + interests + date_range | 🔴 High | 1 день | ⏳ |
| 5 | Поле «Интересы» в профиле + проброс | 🔴 High | 1-2 дня | ⏳ |
| 6 | Согласие ПДн в БД (таблица + API) | 🔴 High | 1 день | ⏳ |
| 7 | Настоящий стриминг (astream_events) | 🟡 Medium | 2-3 дня | ⏳ |
| 8 | hybrid_search с FTS | 🟡 Medium | 1-2 дня | ⏳ |
| 9 | Трассировка в БД agent_traces | 🟡 Medium | 1 день | ⏳ |
| 10 | Workspace news_events | 🟡 Medium | 1 день | ⏳ |
| 11 | X-User-Id проброс из LobeHub | 🟡 Medium | 0.5 дня | ⏳ |
| 12 | ReAct с function calling | 🟢 Low | 2-3 дня | ⏳ |
| 13 | Rate limiting | 🟢 Low | 0.5 дня | ⏳ |
| 14 | model_priority — единый источник | 🟢 Low | 0.5 дня | ⏳ |
| 15 | dialog_context в /chat/stream | 🟢 Low | 15 мин | ⏳ |

---

## 6. СООТВЕТСТВИЕ КРИТЕРИЯМ ПРИЁМКИ (Definition of Done)

Из **MVP_01 §10** и **MVP_02 §10**:

| Критерий | Статус | Комментарий |
|----------|--------|-------------|
| 1. `docker compose up -d --build` поднимает стек | ✅ | 12 сервисов (было 14, убраны 3 MCP) |
| 2. Аноним ведёт диалог, получает ответы с источниками | ⚠ | ✅ Confluence, ❌ news/events не проиндексированы |
| 3. Гость регистрируется/входит, изоляция сессий | ✅ | LobeHub server-mode + Better Auth |
| 4. Новости/события доступны, обновляются ежедневно | ❌ | Нет daily pipeline, нет архивации |
| 5. LLM через LiteLLM с fallback | ✅ | 13 моделей, fallback цепочки |
| 6. Шаги агента пишутся в agent_traces | ⚠ | В JSONL-файлы, не в БД |
| 7. Брендинг «Вопрошалыч» | ✅ | pixel cat, #00aeef, custom.js |
| 8. Лишнее в LobeHub скрыто | ✅ | FEATURE_FLAGS kill-list |
| 9. bot-vk / bot-max работают | ✅ | Есть в compose |
| 10. X-User-Id прокидывается до agent-service | ❌ | LobeHub не пробрасывает |
| 11. Согласие на ПДн при регистрации | ⚠ | Только HTML → localStorage, не в БД |
| 12. `get_events` учитывает интересы | ❌ | Нет interests, нет date_range |

**ИТОГО:** 6/12 критериев полностью выполнены (✅),
3/12 частично (⚠),
3/12 не выполнены (❌).

---

*Документ создан: 2026-07-14. На основе анализа кода
`Submodules/voproshalych_v2/v3/` и требований
`Voproshalych-v3/V3/MVP_01_*`, `MVP_02_*`.*
