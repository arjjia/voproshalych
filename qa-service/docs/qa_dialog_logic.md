# Диалоговая логика QA-сервиса Вопрошалыч (v2)

## Полная схема обработки вопроса

```mermaid
flowchart TD
    subgraph BOT_SERVICE["bot-service :8000"]
        direction TB
        MSG_IN["Входящее сообщение - Telegram / VK"]
        TYPE_CHECK{"Тип сообщения?"}
        VOICE["voice: Я получил голосовое сообщение. Скоро здесь будет распознавание речи."]
        UNSUPPORTED["other: Этот формат сообщения пока не поддерживается."]
        CMD_CHECK{"/команда?"}
        CMD_START["/start - GREETING"]
        CMD_HELP["/help - HELP_CONTACTS"]
        CMD_NEW["Новый диалог - История сброшена!"]
        CMD_SUB["Рассылка - подписка/отписка"]
        CMD_UNKNOWN["Эта команда пока не поддерживается."]
        PENDING["PENDING: Сейчас я попробую ответить... auto-delete"]
        SESSION["get_or_create_active_session"]
        SESSION_ERR{"Сессия?"}
        SESSION_FAIL["DB error - context = None"]
        BUILD_CTX["build_context - max_chars=3000"]
        CTX_RESULT{"history?"}
        CTX_NONE["context = None"]
        CTX_HAS["context = history"]
        QA_CALL["POST http://qa:8004/qa"]

        MSG_IN --> TYPE_CHECK
        TYPE_CHECK -- "voice" --> VOICE
        TYPE_CHECK -- "photo/sticker" --> UNSUPPORTED
        TYPE_CHECK -- "text" --> CMD_CHECK
        CMD_CHECK -- "/start" --> CMD_START
        CMD_CHECK -- "/help" --> CMD_HELP
        CMD_CHECK -- "new dialog" --> CMD_NEW
        CMD_CHECK -- "subscribe" --> CMD_SUB
        CMD_CHECK -- "/command" --> CMD_UNKNOWN
        CMD_CHECK -- "text" --> PENDING --> SESSION --> SESSION_ERR
        SESSION_ERR -. "DB error" .-> SESSION_FAIL --> QA_CALL
        SESSION_ERR -- "OK" --> BUILD_CTX --> CTX_RESULT
        CTX_RESULT -- "empty" --> CTX_NONE --> QA_CALL
        CTX_RESULT -- "has" --> CTX_HAS --> QA_CALL
    end

    QA_CALL -- "HTTP" --> ENTRY

    subgraph QA_SERVICE["qa-service :8004"]
        direction TB
        ENTRY["POST /qa - question max 10000, context opt"]
        VALIDATE{"Pydantic validation?"}
        READY_CHECK{"LightRAG ready?"}
        GLOBAL_TO["asyncio.timeout - total=60s"]

        ENTRY --> VALIDATE
        VALIDATE -. "invalid" .-> ERR_422
        VALIDATE -- "OK" --> READY_CHECK
        READY_CHECK -. "Нет" .-> ERR_503
        READY_CHECK -- "Да" --> GLOBAL_TO

        GLOBAL_TO --> P1_START

        subgraph PHASE1["Phase 1 - classify_and_expand"]
            direction TB
            P1_START["classify_and_expand - question, dialog_context, request_id"]
            P1_POOL{"LLM provider available?"}
            P1_PROMPT["Prompt parts joined by newline:<br/>1. QUERY_CLASSIFY_EXPAND_PROMPT incl GLOSSARY ~1800 chars<br/>2. Dialog context if not empty<br/>3. Question text<br/>4. Output only JSON"]
            P1_LLM["llm_pool.call - temp=0.1, max_tokens=256, timeout=30s"]
            P1_PARSE["Parse JSON: type, expanded_query, context_expanded_query, confidence<br/>Validate type in 1,2,3"]
            P1_RESULT["QuestionClassification"]
            P1_Q_LIMIT{"expanded_query under 1500?"}

            P1_START --> P1_POOL
            P1_POOL -. "no provider" .-> P1_FB
            P1_POOL -- "yes" --> P1_PROMPT --> P1_LLM
            P1_LLM -. "TimeoutError 30s" .-> P1_FB
            P1_LLM -. "Exception" .-> P1_FB
            P1_LLM -- "OK" --> P1_PARSE
            P1_PARSE -. "No JSON" .-> P1_FB
            P1_PARSE -- "OK" --> P1_RESULT --> P1_Q_LIMIT
            P1_Q_LIMIT -- "yes" --> ROUTE
            P1_Q_LIMIT -- "no" --> P1_CUT["truncate to 1500"] --> ROUTE
            P1_FB["fallback: type=1 expanded=original"] --> ROUTE
        end

        ROUTE{"question_type?"}
        ROUTE -- "1 KB" --> T1_SEARCH
        ROUTE -- "2 bot" --> T2_BUILD
        ROUTE -- "3 general" --> T3_BUILD

        subgraph TYPE1["Type 1: Knowledge Base"]
            direction TB
            T1_SEARCH["Phase 2a: LightRAG search<br/>aquery_data - mode=mix, top_k=5<br/>timeout=50s"]
            T1_FORMAT["_format_search_context<br/>chunks with source N tags<br/>entities 15, relationships 10"]
            T1_HAS_CTX{"search_context not empty?"}

            T1_SEARCH --> T1_FORMAT --> T1_HAS_CTX
            T1_SEARCH -. "Timeout/Exception" .-> T1_HAS_CTX

            T1_HAS_CTX -- "yes" --> WC_BUILD
            T1_HAS_CTX -- "no" --> NC_BUILD

            subgraph T1_WITH_CTX["Type 1 with context: SYSTEM_PROMPT_WITH_CONTEXT to JSON"]
                direction TB
                WC_BUILD["Payload build_messages:<br/>system: SYSTEM_PROMPT_WITH_CONTEXT<br/>user: GOLDEN_CHUNKS max 800<br/>+ DIALOG_CONTEXT_PROMPT + context max 1200<br/>+ search_context max 1500<br/>+ question max 500"]
                WC_LLM["llm_pool.call - max_tokens=2048"]
                WC_PARSE["parse_llm_json_response<br/>JSON: relevance_type, relevant_sources,<br/>irrelevant_sources, answer<br/>Fallback: relevance_type=b"]
                WC_REL{"relevance_type?"}

                WC_BUILD --> WC_LLM --> WC_PARSE --> WC_REL
                WC_REL -- "a: relevant" --> WCA_RESULT
                WC_REL -- "b: irrelevant" --> WCB_RESULT

                WCA_RESULT["relevance=a<br/>sources=build_source_links<br/>SourceLink url + label"]
                WCB_RESULT["relevance=b<br/>sources=empty<br/>2 sentences: not found + recommendation"]
            end

            subgraph T1_NO_CTX["Type 1 no context: SYSTEM_PROMPT_NO_CONTEXT"]
                direction TB
                NC_BUILD["Payload build_no_context_messages:<br/>system: SYSTEM_PROMPT_NO_CONTEXT<br/>user: GOLDEN_CHUNKS max 800<br/>+ DIALOG_CONTEXT_PROMPT + context max 1200<br/>+ question max 500<br/>NO search_context"]
                NC_LLM["llm_pool.call - max_tokens=2048"]
                NC_CLEAN["_safe_clean_answer"]
                NC_ERR{"LLM returned empty?"}
                NC_RESULT["relevance=b, sources=empty, 2 sentences"]

                NC_BUILD --> NC_LLM --> NC_CLEAN --> NC_ERR
                NC_ERR -- "no" --> NC_RESULT
                NC_ERR -- "yes" .-> ERR_500
            end
        end

        subgraph TYPE2["Type 2: About bot"]
            direction TB
            T2_BUILD["Payload build_messages:<br/>system: SYSTEM_PROMPT_ABOUT_BOT<br/>user: GOLDEN_CHUNKS max 800<br/>+ DIALOG_CONTEXT_PROMPT + context max 1200<br/>+ question max 500<br/>NO search_context"]
            T2_LLM["llm_pool.call - max_tokens=2048"]
            T2_CLEAN["_safe_clean_answer"]
            T2_ERR{"LLM returned empty?"}
            T2_RESULT["relevance_type=null, sources=empty"]

            T2_BUILD --> T2_LLM --> T2_CLEAN --> T2_ERR
            T2_ERR -- "no" --> T2_RESULT
            T2_ERR -- "yes" .-> ERR_500
        end

        subgraph TYPE3["Type 3: General question"]
            direction TB
            T3_BUILD["Payload build_messages:<br/>system: SYSTEM_PROMPT<br/>user: DIALOG_CONTEXT_PROMPT + context max 1200<br/>+ question max 500<br/>NO GOLDEN_CHUNKS, NO search_context"]
            T3_LLM["llm_pool.call - max_tokens=2048"]
            T3_CLEAN["_safe_clean_answer"]
            T3_ERR{"LLM returned empty?"}
            T3_RESULT["relevance_type=null, sources=empty"]

            T3_BUILD --> T3_LLM --> T3_CLEAN --> T3_ERR
            T3_ERR -- "no" --> T3_RESULT
            T3_ERR -- "yes" .-> ERR_500
        end

        WCA_RESULT --> QAR
        WCB_RESULT --> QAR
        NC_RESULT --> QAR
        T2_RESULT --> QAR
        T3_RESULT --> QAR

        subgraph RESULT["Result"]
            QAR["QAResponse: answer, model,<br/>sources SourceLink list,<br/>relevance_type a or b or null,<br/>expanded_query, context_expanded_query,<br/>keywords, question_type 1 or 2 or 3"]
        end

        GLOBAL_TO -. "TimeoutError" .-> ERR_504
    end

    subgraph ERRORS["Error handling"]
        direction TB
        ERR_422["HTTP 422 - Pydantic Validation Error"]
        ERR_503["HTTP 503 - Service unavailable - LightRAG not init"]
        ERR_504["HTTP 504 - QA pipeline timeout - asyncio.TimeoutError 60s"]
        ERR_500["HTTP 500 - QA pipeline error"]
    end

    ERR_422 --> BOT_FALLBACK_A
    ERR_503 --> BOT_FALLBACK_A
    ERR_504 --> BOT_FALLBACK_A
    ERR_500 --> BOT_FALLBACK_B

    QAR -- "200 OK" --> BOT_PARSE

    BOT_FALLBACK_A["Сервис временно недоступен. Попробуйте позже."]
    BOT_FALLBACK_B["Не удалось получить ответ. Попробуйте повторить вопрос."]

    subgraph BOT_RESPONSE["bot-service: send response"]
        direction TB
        BOT_PARSE["_format_qa_answer"]
        INLINE_CHECK{"relevance_type=a and sources not empty?"}
        INLINE_YES["Inline buttons: Podrobnee N + Like Dislike + New Dialog"]
        INLINE_NO["Buttons: Like Dislike + New Dialog only"]
        BOT_TG["Telegram: InlineKeyboardButton"]
        BOT_VK["VK: OpenLink"]

        BOT_PARSE --> INLINE_CHECK
        INLINE_CHECK -- "yes" --> INLINE_YES --> BOT_TG
        INLINE_YES --> BOT_VK
        INLINE_CHECK -- "no" --> INLINE_NO --> BOT_TG
        INLINE_NO --> BOT_VK
    end

    subgraph BOT_ERRORS["bot-service: send errors"]
        direction TB
        TG_LONG["Telegram msg too long - truncate or answer failed"]
        TG_BAD["TelegramBadRequest - answer failed"]
        TG_ERR["Other send error - answer failed"]
    end

    subgraph LIMITS["Limits"]
        direction LR
        L_Q["question max 10000 - 422"]
        L_DC["dialog_context max 3000 - old messages dropped"]
        L_EXP["expanded_query max 1500"]
        L_GC["golden_chunks max 800 - paragraph cut"]
        L_DCP["dialog_context payload max 1200"]
        L_SC["search_context max 1500 - chunk boundary"]
        L_QU["question payload max 500"]
        L_TOK["LLM response max 2048 tokens"]
        L_ANS["clean_answer max 1500"]
        L_TOP["LightRAG top_k=5"]

        L_Q --> L_DC --> L_EXP --> L_GC --> L_DCP --> L_SC --> L_QU --> L_TOK --> L_ANS --> L_TOP
    end
```

---

## Промт Phase 1: QUERY_CLASSIFY_EXPAND_PROMPT

```
Входит: GLOSSARY_TYUMSU (встроен через f-string)
───────────────────────────────────────────────
QUERY_CLASSIFY_EXPAND_PROMPT = f"""{GLOSSARY_TYUMSU}

Определи тип вопроса и нормализуй его для поиска.

Типы вопросов:
1 — вопрос к базе знаний ТюмГУ (обучение, документы, расписания, ...)
2 — вопрос о самом боте/системе (кто тебя создал, что ты умеешь, ...)
3 — общий вопрос, не связанный с БЗ ТюмГУ (приветствие, шутки, код, ...)

ПРАВИЛО: если вопрос НЕ про университет ТюмГУ и НЕ про бота — тип 3.

Правила нормализации (только для типа 1):
- Используй справочник для расшифровки аббревиатур и сленга
- Аббревиатуры: ВСЕГДА оба варианта — <аббревиатура>, <расшифровка>
- Для типа 2 и 3: expanded_query = оригинальный вопрос без изменений
- НЕ добавляй синонимы, НЕ расширяй, НЕ поясняй

УЧЁТ КОНТЕКСТА ДИАЛОГА (только для типа 1):
Если передана история диалога — проанализируй:
1. Связан ли текущий вопрос с предыдущими?
2. Если связан — расширь запрос терминами из контекста
3. context_expanded_query = самодостаточный поисковый запрос

Верни СТРОГО JSON:
{"type": 1, "expanded_query": "...", "context_expanded_query": "..."}
"""
```

---

## Сводная таблица: Payload по типам вопроса

| Компонент payload | type=1 с контекстом | type=1 без контекста | type=2 (о боте) | type=3 (общий) |
|---|---|---|---|---|
| **system_prompt** | `SYSTEM_PROMPT_WITH_CONTEXT` | `SYSTEM_PROMPT_NO_CONTEXT` | `SYSTEM_PROMPT_ABOUT_BOT` | `SYSTEM_PROMPT` |
| **GOLDEN_CHUNKS** ≤800 | Да | Да | Да | **Нет** |
| **DIALOG_CONTEXT_PROMPT** + dialog_context ≤1200 | Да (если context) | Да (если context) | Да (если context) | Да (если context) |
| **search_context** ≤1500 | Да | **Нет** | **Нет** | **Нет** |
| **question** ≤500 | Да | Да | Да | Да |
| **Формат ответа LLM** | JSON {relevance_type, sources, answer} | Свободный текст (2 предложения) | Свободный текст | Свободный текст |
| **Inline-кнопки** | Да (если relevance_type=a) | Нет | Нет | Нет |

---

## Все промпты и когда они используются

| Промпт | Содержание | Где используется | Размер |
|---|---|---|---|
| `GLOSSARY_TYUMSU` | Справочник аббревиатур, институтов, сленга ТюмГУ | Встроен внутрь QUERY_CLASSIFY_EXPAND_PROMPT | ~1800 символов |
| `QUERY_CLASSIFY_EXPAND_PROMPT` | Классификация типа + нормализация + расширение | Phase 1 — КАЖДЫЙ запрос | ~2040 символов (+GLOSSARY) |
| `SYSTEM_PROMPT` | Поведение Вопрошалыча для общих вопросов: приветствия, болтовня, запрет на код/решения | type=3 (Phase 2) | ~900 символов |
| `SYSTEM_PROMPT_WITH_CONTEXT` | Классификация источников a/b + JSON-ответ. Шаг 1: разделить источники. Шаг 2: сформировать ответ | type=1 + есть search_context (Phase 2) | ~2400 символов |
| `SYSTEM_PROMPT_NO_CONTEXT` | 2 предложения: 1) не нашлось в БЗ, 2) рекомендация из GOLDEN_CHUNKS или догадка | type=1 + нет search_context (Phase 2) | ~1500 символов |
| `SYSTEM_PROMPT_ABOUT_BOT` | Информация о боте, команде, технологиях, источниках данных | type=2 (Phase 2) | ~1100 символов |
| `DIALOG_CONTEXT_PROMPT` | Инструкция: использовать историю как контекст, приоритет у документов ТюмГУ | type=1 (обе ветки), type=2, type=3 — ЕСЛИ context не пустой | ~200 символов |
| `GOLDEN_CHUNKS` | Базовая информация о ТюмГУ (пока placeholder) | type=1 (обе ветки), type=2 | ~80 символов (placeholder) |
| `HOLIDAY_GREETING_PROMPT` | Генерация праздничных поздравлений | Отдельный endpoint /holiday-greeting | ~350 символов |

---

## Шаблонные сообщения bot-service: когда отправляются

| Сообщение | Когда отправляется | Источник в коде |
|---|---|---|
| «Сервис временно недоступен. Попробуйте позже.» | QA timeout, QA 503/504, QA 429, QA любая HTTP-ошибка, DB ошибки диалога/подписки/фидбека | `SERVICE_UNAVAILABLE` (messages.py) |
| «Не удалось получить ответ. Попробуйте повторить вопрос.» | Неожиданная ошибка QA, ошибка отправки в Telegram | `ANSWER_FAILED` (messages.py) |
| «Вы уже оценили этот ответ.» | Повторный клик like/dislike на один ответ | `FEEDBACK_ALREADY_RATED` |
| «Эта команда пока не поддерживается.» | Неизвестная /команда | `UNKNOWN_COMMAND` |
| «Сейчас я попробую ответить на этот вопрос, это может занять какое-то время...» | Перед каждым QA-запросом (auto-delete) | `PENDING_MESSAGE` |
| «История сброшена! Задавайте новый вопрос 🔄» | Кнопка «Новый диалог» | `DIALOG_RESET` |
| «Вы подписались на поздравления с праздниками!» | Успешная подписка | `SUBSCRIBED` |
| «Вы отписались от поздравлений.» | Успешная отписка | `UNSUBSCRIBED` |
| «Рад помочь! 😻» | Лайк сохранён | `FEEDBACK_LIKE` |
| «Спасибо за обратную связь, постараюсь стать лучше! 🐱» | Дизлайк сохранён | `FEEDBACK_DISLIKE` |
| «Я получил голосовое сообщение. Скоро здесь будет распознавание речи.» | Voice message | `VOICE_STUB` |
| «Этот формат сообщения пока не поддерживается.» | Photo, sticker, video, etc. | `UNSUPPORTED_FORMAT` |
| GREETING (многострочный) | /start | `GREETING` |
| HELP_CONTACTS (многострочный) | /help или «📋 помощь» | `HELP_CONTACTS` |

### Шаблонные сообщения qa-service

| HTTP статус | Сообщение | Когда |
|---|---|---|
| 422 | Pydantic Validation Error | question пустой или >10000 |
| 503 | «Service unavailable» | LightRAG не инициализирован |
| 504 | «QA pipeline timeout» | Глобальный таймаут 60s исчерпан |
| 500 | «QA pipeline error: {exception}» | Любое необработанное исключение в pipeline |

---

## LLM Pool: Fallback-цепочка провайдеров

```
Приоритет: mistral → openrouter → gigachat
(config: model_priority = "mistral,openrouter")

MistralProvider:
  • Модель: open-mistral-nemo
  • Транспорт: requests + HTTPAdapter
  • Retry: total=3, backoff=0.2, статус коды [502,503,504,429]
  • Timeout: connect=5s, read=mistral_timeout (30s)
  • Connection: close (каждый запрос)
  • Warmup: при старте (lifespan)
  • НЕ retry: 400, 401, 403

OpenRouterProvider:
  • Модель: nvidia/nemotron-3-super-120b-a12b:free
  • Fallback: openrouter/free

GigaChatProvider:
  • Авторизация по client_id + client_secret
```

---

## Таблица всех лимитов

| Лимит | Значение | Где | Что при превышении |
|---|---|---|---|
| question | 10 000 символов | QARequest (Pydantic) | 422 Validation Error |
| dialog_context (сборка) | 3 000 символов | bot-service: build_context() | Старые сообщения не попадают в контекст |
| expanded_query | 1 500 символов | question_router.py | Обрезка `[:1500]` |
| context_expanded_query | 1 500 символов | question_router.py | Обрезка `[:1500]` |
| golden_chunks в payload | 800 символов | payload_builder.py | Обрезка по границе абзаца |
| dialog_context в payload | 1 200 символов | payload_builder.py | Жёсткая обрезка |
| search_context в payload | 1 500 символов | payload_builder.py | Обрезка по границе `\n---\n` |
| question в payload | 500 символов | payload_builder.py | Жёсткая обрезка |
| ответ LLM (max_tokens) | 2 048 токенов | llm/config.py | LLM обрежет генерацию |
| clean_answer | 1 500 символов | response_processor.py | Обрезка по абзацу/строке |
| LightRAG top_k | 5 | qa.py SEARCH_TOP_K | — |
| Глобальный таймаут pipeline | 60s | qa.py _get_timeouts() | HTTP 504 |
| Phase 1 таймаут (классификация) | 30s | config: query_expansion_timeout | fallback type=1 |
| Phase 2a таймаут (LightRAG) | 50s (total-10) | qa.py _get_timeouts() | search_context='' |
| Phase 2b таймаут (генерация) | 60s | config: answer_generation_timeout | HTTP 504 (от глобального) |
| Mistral connect timeout | 5s | mistral.py | Retry urllib3 |
| Mistral read timeout | 30s | config: mistral_timeout | Retry urllib3 |
| Mistral retry total | 3 | mistral.py HTTPAdapter | После 3 попыток → fallback провайдер |

---

## Релевантность контекста (типы a/b) — только type=1 с контекстом

| Тип | relevant_sources | Ответ | «Подробнее» | Inline-кнопки |
|---|---|---|---|---|
| **a** | Не пустой | Полный ответ из контекста БЗ | Кнопки «Подробнее N» с URL | Да |
| **b** | Пустой | 2 предложения: 1) не нашлось в БЗ, 2) рекомендация/догадка | Нет | Нет |

---

## Модель ответа QAResponse

```
QAResponse {
    answer: str                          # Очищенный текст без markdown
    model: str                           # Имя модели (open-mistral-nemo)
    sources: list[SourceLink]            # URL-кнопки «Подробнее N»
    expanded_query: str | None           # Нормализованный запрос (type=1)
    context_expanded_query: str | None   # Расширенный с контекстом (type=1)
    keywords: dict | None                # {high_level: [], low_level: []}
    question_type: int                   # 1=БЗ, 2=система, 3=общий
    relevance_type: str | None           # 'a' | 'b' | null
}
```

---

## Конфигурация таймаутов

| Параметр | Значение | Назначение |
|---|---|---|
| `mistral_timeout` | 30s | Read timeout для Mistral API |
| `keyword_extraction_timeout` | 15s | Извлечение ключевых слов LightRAG |
| `query_expansion_timeout` | 30s | Phase 1: классификация вопроса |
| `answer_generation_timeout` | 60s | Phase 2b: генерация ответа |
| `graph_building_timeout` | 600s | Построение графа знаний |
| `LLM_CALL_DELAY` | 0.5s | Задержка между LLM-вызовами LightRAG |
| `MERGE_PRESET` | `score_cfg_a` | Стратегия слияния чанков (vector=1.2, entity=0.8, relation=0.6) |
