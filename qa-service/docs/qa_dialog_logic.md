# Диалоговая логика QA-сервиса Вопрошалыч (v2)

## Полная схема обработки вопроса

```mermaid
flowchart TD
    subgraph BOT_SERVICE["bot-service :8000"]
        direction TB
        MSG_IN["Входящее сообщение<br/>Telegram / VK"]
        TYPE_CHECK{"Тип сообщения?"}
        VOICE["«Я получил голосовое сообщение.<br/>Скоро здесь будет распознавание речи.»"]
        UNSUPPORTED["«Этот формат сообщения<br/>пока не поддерживается.»"]
        CMD_CHECK{"/команда?"}
        CMD_START["/start → GREETING"]
        CMD_HELP["/help → HELP_CONTACTS"]
        CMD_NEW["🔄 новый диалог →<br/>«История сброшена! Задавайте новый вопрос 🔄»"]
        CMD_SUB["🔔 рассылка →<br/>«Вы подписались...» / «Вы отписались...»"]
        CMD_UNKNOWN["«Эта команда пока не поддерживается.»"]
        PENDING["Отправить PENDING:<br/>«Сейчас я попробую ответить на этот вопрос,<br/>это может занять какое-то время...»<br/>auto-delete после ответа"]
        SESSION["get_or_create_active_session(user_id)"]
        SESSION_ERR{"Сессия?"}
        SESSION_FAIL["DB error → context = None"]
        BUILD_CTX["build_context(session_id, max_chars=3000)<br/>SELECT messages ORDER BY id DESC<br/>Формат: «Пользователь: …» / «Бот: …»"]
        CTX_RESULT{"history?"}
        CTX_NONE["context = None"]
        CTX_HAS["context = history"]
        QA_CALL["POST http://qa:8004/qa<br/>{question, context?}<br/>X-Request-ID: uuid8"]

        MSG_IN --> TYPE_CHECK
        TYPE_CHECK -- "voice" --> VOICE
        TYPE_CHECK -- "photo/sticker/..." --> UNSUPPORTED
        TYPE_CHECK -- "text" --> CMD_CHECK
        CMD_CHECK -- "/start" --> CMD_START
        CMD_CHECK -- "/help | 📋 помощь" --> CMD_HELP
        CMD_CHECK -- "🔄 новый диалог" --> CMD_NEW
        CMD_CHECK -- "🔔 рассылка" --> CMD_SUB
        CMD_CHECK -- "/command" --> CMD_UNKNOWN
        CMD_CHECK -- "Обычный текст" --> PENDING --> SESSION --> SESSION_ERR
        SESSION_ERR -. "DB error" .-> SESSION_FAIL --> QA_CALL
        SESSION_ERR -- "OK" --> BUILD_CTX --> CTX_RESULT
        CTX_RESULT -- "Пусто" --> CTX_NONE --> QA_CALL
        CTX_RESULT -- "Непусто" --> CTX_HAS --> QA_CALL
    end

    QA_CALL -- "HTTP" --> ENTRY

    subgraph QA_SERVICE["qa-service :8004"]
        direction TB
        ENTRY["POST /qa<br/>QARequest {question ≤10000, context?}"]
        VALIDATE{"Pydantic<br/>validation?"}
        READY_CHECK{"LightRAG<br/>ready?"}
        GLOBAL_TO["asyncio.timeout(total=60s)"]

        ENTRY --> VALIDATE
        VALIDATE -. "question пустой или >10000" .-> ERR_422
        VALIDATE -- "OK" --> READY_CHECK
        READY_CHECK -. "Нет" .-> ERR_503
        READY_CHECK -- "Да" --> GLOBAL_TO

        GLOBAL_TO --> P1_START

        subgraph PHASE1["Phase 1: classify_and_expand()"]
            direction TB
            P1_START["classify_and_expand(<br/>question, dialog_context, request_id)"]
            P1_POOL{"LLM provider<br/>доступен?"}
            P1_PROMPT["Сборка prompt (части через \\n\\n):<br/>1. QUERY_CLASSIFY_EXPAND_PROMPT<br/>   (включает GLOSSARY_TYUMSU ~1800 симв.)<br/>2. «История диалога:\\n{dialog_context}»<br/>   (ТОЛЬКО если context не пустой)<br/>3. «Вопрос: {question}»<br/>4. «Ответ (только JSON):»"]
            P1_LLM["llm_pool.call(<br/>prompt, temperature=0.1, max_tokens=256)<br/>timeout = query_expansion_timeout = 30s"]
            P1_PARSE["_parse_classification_response()<br/>Regex поиск JSON {type, expanded_query,<br/>context_expanded_query, confidence}<br/>Валидация: type ∈ {1,2,3}"]
            P1_RESULT["QuestionClassification {<br/>question_type, expanded_query,<br/>context_expanded_query, confidence}"]
            P1_Q_LIMIT{"expanded_query ≤ 1500?"}

            P1_START --> P1_POOL
            P1_POOL -. "Нет провайдера" .-> P1_FB
            P1_POOL -- "Да" --> P1_PROMPT --> P1_LLM
            P1_LLM -. "TimeoutError (30s)" .-> P1_FB
            P1_LLM -. "Exception" .-> P1_FB
            P1_LLM -- "OK" --> P1_PARSE
            P1_PARSE -. "No JSON" .-> P1_FB
            P1_PARSE -- "OK" --> P1_RESULT --> P1_Q_LIMIT
            P1_Q_LIMIT -- "Да" --> ROUTE
            P1_Q_LIMIT -- "Нет" --> P1_CUT["[:1500]"] --> ROUTE
            P1_FB["fallback: type=1,<br/>expanded=оригинал"] --> ROUTE
        end

        ROUTE{"question_type?"}
        ROUTE -- "1 → База знаний" --> T1_SEARCH
        ROUTE -- "2 → О боте" --> T2_BUILD
        ROUTE -- "3 → Общий" --> T3_BUILD

        subgraph TYPE1["Тип 1: База знаний"]
            direction TB
            T1_SEARCH["Phase 2a: LightRAG search<br/>rag.aquery_data(search_query,<br/>mode=mix, top_k=5)<br/>timeout = total - 10 ≈50s"]
            T1_FORMAT["_format_search_context(data)<br/>chunks → «--- Найденная информация ---»<br/>каждый chunk с [источник N] если URL<br/>entities[:15], desc[:100]<br/>relationships[:10], desc[:100]"]
            T1_HAS_CTX{"search_context.strip()<br/>не пустой?"}

            T1_SEARCH --> T1_FORMAT --> T1_HAS_CTX
            T1_SEARCH -. "Timeout/Exception →<br/>search_context = ''" .-> T1_HAS_CTX

            T1_HAS_CTX -- "Да" --> WC_BUILD
            T1_HAS_CTX -- "Нет" --> NC_BUILD

            subgraph T1_WITH_CTX["Тип 1 с контекстом БЗ: SYSTEM_PROMPT_WITH_CONTEXT → JSON"]
                direction TB
                WC_BUILD["Payload (build_messages):<br/>─────────────────<br/>system: SYSTEM_PROMPT_WITH_CONTEXT<br/>user:<br/>  1. GOLDEN_CHUNKS ≤800<br/>  2. DIALOG_CONTEXT_PROMPT + dialog_context ≤1200<br/>     (если context не пустой)<br/>  3. search_context ≤1500<br/>  4. question ≤500"]
                WC_LLM["llm_pool.call(messages)<br/>max_tokens=2048"]
                WC_PARSE["parse_llm_json_response(raw)<br/>regex поиск JSON {relevance_type,<br/>relevant_sources, irrelevant_sources, answer}<br/>fallback: _parse_structured_text_fallback()<br/>если JSON не найден → relevance_type='b'"]
                WC_REL{"relevance_type?"}

                WC_BUILD --> WC_LLM --> WC_PARSE --> WC_REL
                WC_REL -- "a: релевантный" --> WCA_RESULT
                WC_REL -- "b: нерелевантный" --> WCB_RESULT

                WCA_RESULT["relevance='a'<br/>answer = format_answer(parsed.answer)<br/>sources = build_source_links(<br/>  relevant_sources, source_index)<br/>→ [SourceLink{url, 'Подробнее N'}]"]
                WCB_RESULT["relevance='b'<br/>answer = format_answer(parsed.answer)<br/>sources = []<br/>(2 предложения: не нашлось + рекомендация)"]
            end

            subgraph T1_NO_CTX["Тип 1 без контекста БЗ: SYSTEM_PROMPT_NO_CONTEXT"]
                direction TB
                NC_BUILD["Payload (build_no_context_messages):<br/>─────────────────<br/>system: SYSTEM_PROMPT_NO_CONTEXT<br/>user:<br/>  1. GOLDEN_CHUNKS ≤800<br/>  2. DIALOG_CONTEXT_PROMPT + dialog_context ≤1200<br/>     (если context не пустой)<br/>  3. question ≤500<br/>(search_context ОТСУТСТВУЕТ)"]
                NC_LLM["llm_pool.call(messages)<br/>max_tokens=2048"]
                NC_CLEAN["_safe_clean_answer():<br/>clean_markdown() + format_answer()"]
                NC_ERR{"LLM вернул пустой?"}
                NC_RESULT["relevance='b', sources=[],<br/>answer = чистый текст (2 предложения)"]

                NC_BUILD --> NC_LLM --> NC_CLEAN --> NC_ERR
                NC_ERR -- "Нет" --> NC_RESULT
                NC_ERR -- "Да → ValueError → HTTP 500" .-> ERR_500
            end
        end

        subgraph TYPE2["Тип 2: Вопрос о боте"]
            direction TB
            T2_BUILD["Payload (build_messages):<br/>─────────────────<br/>system: SYSTEM_PROMPT_ABOUT_BOT<br/>user:<br/>  1. GOLDEN_CHUNKS ≤800<br/>  2. DIALOG_CONTEXT_PROMPT + dialog_context ≤1200<br/>     (если context не пустой)<br/>  3. question ≤500<br/>(search_context ОТСУТСТВУЕТ)"]
            T2_LLM["llm_pool.call(messages)<br/>max_tokens=2048"]
            T2_CLEAN["_safe_clean_answer()"]
            T2_ERR{"LLM вернул пустой?"}
            T2_RESULT["relevance_type=null, sources=[]"]

            T2_BUILD --> T2_LLM --> T2_CLEAN --> T2_ERR
            T2_ERR -- "Нет" --> T2_RESULT
            T2_ERR -- "Да → ValueError → HTTP 500" .-> ERR_500
        end

        subgraph TYPE3["Тип 3: Общий вопрос"]
            direction TB
            T3_BUILD["Payload (build_messages):<br/>─────────────────<br/>system: SYSTEM_PROMPT<br/>user:<br/>  1. DIALOG_CONTEXT_PROMPT + dialog_context ≤1200<br/>     (если context не пустой)<br/>  2. question ≤500<br/>(GOLDEN_CHUNKS НЕТ)<br/>(search_context НЕТ)"]
            T3_LLM["llm_pool.call(messages)<br/>max_tokens=2048"]
            T3_CLEAN["_safe_clean_answer()"]
            T3_ERR{"LLM вернул пустой?"}
            T3_RESULT["relevance_type=null, sources=[]"]

            T3_BUILD --> T3_LLM --> T3_CLEAN --> T3_ERR
            T3_ERR -- "Нет" --> T3_RESULT
            T3_ERR -- "Да → ValueError → HTTP 500" .-> ERR_500
        end

        WCA_RESULT --> QAR
        WCB_RESULT --> QAR
        NC_RESULT --> QAR
        T2_RESULT --> QAR
        T3_RESULT --> QAR

        subgraph RESULT["Результат"]
            QAR["QAResponse {<br/>answer, model,<br/>sources: [SourceLink{url, label}],<br/>relevance_type: a | b | null,<br/>expanded_query, context_expanded_query,<br/>keywords, question_type: 1|2|3}"]
        end

        GLOBAL_TO -. "TimeoutError" .-> ERR_504
    end

    subgraph ERRORS["Обработка ошибок"]
        direction TB
        ERR_422["HTTP 422<br/>Pydantic Validation Error"]
        ERR_503["HTTP 503<br/>«Service unavailable»<br/>LightRAG не инициализирован"]
        ERR_504["HTTP 504<br/>«QA pipeline timeout»<br/>asyncio.TimeoutError (60s)"]
        ERR_500["HTTP 500<br/>«QA pipeline error: {e}»"]
    end

    ERR_422 --> BOT_FALLBACK_A
    ERR_503 --> BOT_FALLBACK_A
    ERR_504 --> BOT_FALLBACK_A
    ERR_500 --> BOT_FALLBACK_B

    QAR -- "200 OK" --> BOT_PARSE

    BOT_FALLBACK_A["«Сервис временно недоступен.<br/>Попробуйте позже.»"]
    BOT_FALLBACK_B["«Не удалось получить ответ.<br/>Попробуйте повторить вопрос.»"]

    subgraph BOT_RESPONSE["bot-service: отправка ответа"]
        direction TB
        BOT_PARSE["_format_qa_answer(qa_result)"]
        INLINE_CHECK{"relevance_type='a'<br/>и sources не пустой?"}
        INLINE_YES["+ inline-кнопки «Подробнее N»<br/>+ ❤️ 👎 | 🔄 Новый диалог"]
        INLINE_NO["+ ❤️ 👎 | 🔄 Новый диалог<br/>(без «Подробнее»)"]
        BOT_TG["Telegram:<br/>InlineKeyboardButton(url=...)"]
        BOT_VK["VK:<br/>OpenLink(link=..., label=...)"]

        BOT_PARSE --> INLINE_CHECK
        INLINE_CHECK -- "Да" --> INLINE_YES --> BOT_TG
        INLINE_YES --> BOT_VK
        INLINE_CHECK -- "Нет" --> INLINE_NO --> BOT_TG
        INLINE_NO --> BOT_VK
    end

    subgraph BOT_ERRORS["bot-service: ошибки при отправке"]
        direction TB
        TG_LONG["Telegram: сообщение слишком длинное<br/>→ truncate, если не получается →<br/>«Не удалось получить ответ...»"]
        TG_BAD["TelegramBadRequest<br/>→ «Не удалось получить ответ...»"]
        TG_ERR["Любая другая ошибка отправки<br/>→ «Не удалось получить ответ...»"]
    end

    subgraph LIMITS["Карта лимитов"]
        direction LR
        L_Q["question ≤ 10 000 символов<br/>422 при превышении"]
        L_DC["dialog_context ≤ 3 000<br/>старые сообщения отбрасываются"]
        L_EXP["expanded_query ≤ 1 500<br/>[:1500]"]
        L_GC["golden_chunks ≤ 800<br/>обрезка по абзацу"]
        L_DCP["dialog_context в payload ≤ 1 200<br/>жёсткая обрезка"]
        L_SC["search_context ≤ 1 500<br/>обрезка по \\n---\\n"]
        L_QU["question в payload ≤ 500<br/>жёсткая обрезка"]
        L_TOK["ответ LLM ≤ 2 048 токенов"]
        L_ANS["clean_answer ≤ 1 500<br/>обрезка по абзацу/строке"]
        L_TOP["LightRAG top_k = 5"]

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
