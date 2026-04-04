# Пользовательский пайплайн: Вопрос пользователя → Ответ бота

## Общее описание

Данный документ описывает полный путь запроса пользователя от отправки сообщения в мессенджере до получения ответа от LLM с использованием базы знаний ТюмГУ.

---

### Mermaid диаграмма: полный сценарий вопроса (v2 - детальная)

```mermaid
sequenceDiagram
    autonumber
    participant User as Пользователь
    participant TelegramAPI as Telegram API
    participant BotCore as bot-core<br/>(FastAPI)
    participant QAService as qa-service<br/>(FastAPI)
    participant Postgres as PostgreSQL<br/>(pgvector + AGE)
    participant MistralAPI as Mistral API
    participant GigaChatAPI as GigaChat API
    participant OpenRouterAPI as OpenRouter API

    %% ═══════════════════════════════════════════════════════════
    %% ОБЛАСТЬ 1: Telegram Adapter (bots/telegram/bot.py)
    %% ═══════════════════════════════════════════════════════════
        Note over User,TelegramAPI: === ОБЛАСТЬ 1: Telegram Adapter ===
        
        User->>TelegramAPI: 1. Отправляет вопрос<br/>"Какие правила приёма?"
        TelegramAPI->>TelegramAPI: 2. aiogram Dispatcher<br/>получает Update
        
        activate TelegramAPI
        TelegramAPI->>TelegramAPI: 3. handle_message(message)<br/>(bot.py:145)
        TelegramAPI->>TelegramAPI: 4. detect_message_type()
        
        alt message_type is text
            TelegramAPI->>TelegramAPI: 5. should_show_pending_message()<br/>(bot.py:308)
            TelegramAPI->>TelegramAPI: 6. message.answer("Ищу ответ...")<br/>(bot.py:157)
        end
        
        TelegramAPI->>TelegramAPI: 7. CoreClient._build_payload()<br/>(bot.py:99)
            Note over TelegramAPI:IncomingMessage JSON<br/>{platform, user_id, chat_id, text, message_type, metadata}
        TelegramAPI->>TelegramAPI: 8. CoreClient.process_message()<br/>(bot.py:60)
        TelegramAPI->>BotCore: 9. POST /messages (httpx)<br/>(bot.py:71)
        deactivate TelegramAPI

    %% ═══════════════════════════════════════════════════════════
    %% ОБЛАСТЬ 2: Bot-Core (core/main.py + services/)
    %% ═══════════════════════════════════════════════════════════
        Note over BotCore,QAService: === ОБЛАСТЬ 2: Bot-Core ===
        
        activate BotCore
        BotCore->>BotCore: 10. process_message() endpoint<br/>(main.py:30)
        BotCore->>BotCore: 11. BotService.handle_message()<br/>(bot_service.py:25)
        
            Note over BotCore,Postgres: -- Под-область: UserService --
            
            BotCore->>BotCore: 12. UserService.upsert_user()<br/>(bot_service.py:35)
            BotCore->>Postgres: 13. SELECT * FROM users<br/>WHERE platform=? AND platform_user_id=?
            
            alt Пользователь НЕ найден
                Postgres-->>BotCore: 14. None
                BotCore->>Postgres: 15. INSERT INTO users<br/>(platform, platform_user_id, ...)
                Postgres-->>BotCore: 16. RETURNING id
            else Пользователь найден
                Postgres-->>BotCore: 17. User row
                BotCore->>Postgres: 18. UPDATE users SET<br/>username=?, first_name=?, ...
            end
            Postgres-->>BotCore: 19. COMMIT
        
        BotCore->>BotCore: 20. Проверка message_type<br/>(bot_service.py:37)
        
        alt message_type is text
            BotCore->>BotCore: 21. _handle_text_message()<br/>(bot_service.py:91)
            BotCore->>BotCore: 22. normalized = text.strip().lower()
            
            alt normalized is /start
                BotCore->>BotCore: 23. _build_start_response()<br/>(bot_service.py:208)
                BotCore->>BotCore: 24. _build_start_buttons()
            else
                BotCore->>BotCore: 26. _ask_qa_service()<br/>(bot_service.py:168)
                BotCore->>QAService: 27. QAServiceClient.ask()<br/>(qa_service_client.py:56)
            end
        end
        opt message_type is voice
            BotCore->>BotCore: 28. _handle_voice_message()<br/>(bot_service.py:122)
            Note over BotCore: Заглушка - скоро появится STT
        end
        opt unsupported message type
            BotCore->>BotCore: 29. _build_unsupported_message_response()<br/>(bot_service.py:144)
        end
        deactivate BotCore

    %% ═══════════════════════════════════════════════════════════
    %% ОБЛАСТЬ 3: QAServiceClient Retry (services/qa_service_client.py)
    %% ═══════════════════════════════════════════════════════════
        Note over QAService,BotCore: === ОБЛАСТЬ 3: Retry Logic ===
        
        loop max 3 попытки (1s → 2s → 4s → 8s)
            activate QAService
            QAService->>QAService: 30. httpx.Client.post("/qa")<br/>(qa_service_client.py:74)
            
            alt Успех (200)
                QAService-->>BotCore: 31. {answer, model, sources}<br/>(qa_service_client.py:106)
                deactivate QAService
            end
            opt 503 (Unavailable)
                QAService--xQAService: 32. HTTP 503
                QAService->>QAService: 33. time.sleep(backoff)<br/>(qa_service_client.py:89)
                Note over QAService: backoff increases
            end
            opt 500 (Internal Error)
                QAService--xQAService: 34. HTTP 500
                QAService->>QAService: 35. time.sleep(backoff)
            end
            opt 429 (Rate Limited)
                QAService--xQAService: 36. HTTP 429
                QAService->>QAService: 37. time.sleep(backoff * 2)<br/>(double backoff for rate limit)
            end
            opt Timeout
                QAService--xQAService: 38. httpx.TimeoutException
                QAService->>QAService: 39. time.sleep(backoff)
            end
        end
        
        alt После всех попыток - ошибка
            QAService--xBotCore: 40. QAServiceTimeout / QAServiceUnavailable<br/>(qa_service_client.py:144)
            BotCore->>BotCore: 41. Обработка исключения<br/>(bot_service.py:189-206)
            BotCore->>BotCore: 42. Текст ошибки для пользователя
        end

    %% ═══════════════════════════════════════════════════════════
    %% ОБЛАСТЬ 4: QA-Service (qa/api/routes/qa.py)
    %% ═══════════════════════════════════════════════════════════
        Note over QAService,Postgres: === ОБЛАСТЬ 4: QA Processing ===
        
        activate QAService
        QAService->>QAService: 43. ask_question(QARequest)<br/>(qa.py:92)
        QAService->>QAService: 44. USE_LIGHT_RAG = os.getenv("USE_LIGHT_RAG")<br/>(qa.py:100)
        
        alt USE_LIGHT_RAG is "true"
            Note over QAService,MistralAPI: ═══ LightRAG Primary (20s timeout) ═══
            
            QAService->>QAService: 45. asyncio.wait_for(<br/>_query_lightrag(), timeout=20)<br/>(qa.py:107)
            QAService->>QAService: 46. LightRAG.aquery(question)<br/>(qa.py:37)
            
                Note over QAService,MistralAPI: -- Под-область: LightRAG Query Flow --
                
                QAService->>QAService: 47. lightrag_adapter.llm_model_func()<br/>(lightrag_adapter.py:15)
                QAService->>QAService: 48. lightrag_adapter._embedding_func()<br/>(lightrag_adapter.py:42)
                QAService->>QAService: 49. get_embeddings_batch(texts)<br/>(embedding.py:45)
                QAService->>QAService: 50. SentenceTransformer.encode()<br/>(embedding.py:41)
                QAService->>QAService: 51. deepvk/USER-bge-m3 → 1024-dim vector
                
                Note over QAService,Postgres: Внутри LightRAG:<br/>1. Keyword extraction<br/>2. Vector search (PGVectorStorage)<br/>3. Graph search (PGGraphStorage)<br/>4. Full-text search<br/>5. Merge & Rank results
                
                QAService->>Postgres: 52. SELECT ... FROM chunks<br/>JOIN embeddings<br/>ORDER BY vector <=> query<br/>LIMIT top_k
                Postgres-->>QAService: 53. vector_results (chunks)
                
                QAService->>Postgres: 54. MATCH (n)-[r]->(m)<br/>WHERE n.name IN keywords<br/>(Cypher via Apache AGE)
                Postgres-->>QAService: 55. graph_results (entities + relations)
                
                QAService->>QAService: 56. merge_and_rank(<br/>vector_results, graph_results)
            
            QAService->>QAService: 57. llm_pool.call(prompt)<br/>(llm/pool.py:71)
            
            alt LightRAG успех (< 20s)
                QAService-->>QAService: 58. LLMResponse(content)<br/>(llm/pool.py:124)
                QAService-->>QAService: 59. QAResponse(answer, model="lightrag-mix")
                
            else LightRAG timeout/error
                QAService--xQAService: 60. TimeoutError / Exception
                Note over QAService,MistralAPI: ═══ Classic RAG Fallback (15s timeout) ═══
                
                QAService->>QAService: 61. asyncio.wait_for(<br/>_query_classic_rag(), timeout=15)<br/>(qa.py:128)
                
                    Note over QAService,MistralAPI: -- Под-область: Classic RAG --
                    
                    QAService->>QAService: 62. get_embedding(question)<br/>(kb/embedding.py:31)
                    QAService->>QAService: 63. SentenceTransformer.encode(text)<br/>(kb/embedding.py:41)
                    QAService->>Postgres: 64. SELECT ... FROM chunks c<br/>JOIN embeddings e ON c.id = e.chunk_id<br/>ORDER BY e.embedding_vector <=> :embedding<br/>LIMIT 3
                    Postgres-->>QAService: 65. Top-3 chunks (text, title, source_url)
                    
                    QAService->>QAService: 66. build_context_from_chunks(chunks)<br/>(kb/search.py)
                    QAService->>QAService: 67. SYSTEM_PROMPT_WITH_CONTEXT<br/>+ context + question<br/>(prompts.py)
                
                QAService->>QAService: 68. llm_pool.call(prompt)<br/>(llm/pool.py:71)
            
        else
            Note over QAService,MistralAPI: Classic RAG Only (USE_LIGHT_RAG=false)
            
            QAService->>QAService: 69. _query_classic_rag(question)<br/>(qa.py:48)
            QAService->>QAService: 70. get_embedding() → search_chunks()
            QAService->>Postgres: 71. Vector search (top_k=3)
            Postgres-->>QAService: 72. chunks
            QAService->>QAService: 73. build_context_from_chunks() + prompt
                QAService->>QAService: 74. llm_pool.call(prompt)
        end
        deactivate QAService

    %% ═══════════════════════════════════════════════════════════
    %% ОБЛАСТЬ 5: LLM Pool (llm/pool.py + providers/)
    %% ═══════════════════════════════════════════════════════════
        Note over MistralAPI,OpenRouterAPI: === ОБЛАСТЬ 5: LLM Pool (Fallback) ===
        
        QAService->>QAService: 75. llm_pool.call(prompt)<br/>(llm/pool.py:71)
        QAService->>QAService: 76. select_model()<br/>(llm/pool.py:56)
        QAService->>QAService: 77. get_available_providers()
        
            Note over QAService,MistralAPI: --- Try Mistral ---
            
            alt MistralProvider.is_available()
                QAService->>QAService: 78. MistralProvider.generate()
                QAService->>MistralAPI: 79. POST /v1/chat/completions
                activate MistralAPI
                MistralAPI-->>QAService: 80. Response JSON
                deactivate MistralAPI
                QAService-->>QAService: 81. LLMResponse
                
            else Mistral unavailable
                QAService->>QAService: 82. Try GigaChat
                Note over QAService,GigaChatAPI: --- Try GigaChat ---
                
                alt GigaChatProvider.is_available()
                    QAService->>QAService: 83. GigaChatProvider.generate()
                    QAService->>GigaChatAPI: 84. POST /llm/v1/chat/completions
                    activate GigaChatAPI
                    GigaChatAPI-->>QAService: 85. Response JSON
                    deactivate GigaChatAPI
                    QAService-->>QAService: 86. LLMResponse
                    
                else GigaChat unavailable
                    QAService->>QAService: 87. Try OpenRouter
                    Note over QAService,OpenRouterAPI: --- Try OpenRouter ---
                    
                    QAService->>QAService: 88. OpenRouterProvider.generate()
                    QAService->>OpenRouterAPI: 89. POST /v1/chat/completions
                    activate OpenRouterAPI
                    OpenRouterAPI-->>QAService: 90. Response JSON
                    deactivate OpenRouterAPI
                    QAService-->>QAService: 91. LLMResponse
                    
                    opt All failed
                        QAService->>QAService: 92. raise ValueError
                    end
                end
            end

    %% ═══════════════════════════════════════════════════════════
    %% ОБЛАСТЬ 6: Формирование ответа и возврат
    %% ═══════════════════════════════════════════════════════════
        Note over BotCore,TelegramAPI: === ОБЛАСТЬ 6: Response Formation ===
        
        QAService->>QAService: 96. Формирование QAResponse<br/>(qa.py:81-85)
            alt chunks найдены
                QAService->>QAService: 97. sources = [c.source_url for c in chunks]
            else
                QAService->>QAService: 98. sources = []
            end
        QAService-->>BotCore: 99. QAResponse {answer, model, sources}<br/>(qa.py:75)
        
        BotCore->>BotCore: 100. Обработка ответа<br/>(bot_service.py:110)
        BotCore->>BotCore: 101. _build_feedback_buttons()<br/>(bot_service.py:263)
            Note over BotCore: Создание кнопок
        BotCore->>BotCore: 102. BotResponse(actions=[OutgoingAction(...)])
        BotCore-->>TelegramAPI: 103. BotResponse JSON<br/>(main.py:42)
        activate TelegramAPI
        TelegramAPI->>TelegramAPI: 104. handle_message() получает ответ<br/>(bot.py:207)
        TelegramAPI->>TelegramAPI: 105. build_inline_keyboard(buttons)<br/>(bot.py:251)
        TelegramAPI->>TelegramAPI: 106. message.answer(text, reply_markup)<br/>(bot.py:209)
        
        alt Было pending message
            TelegramAPI->>TelegramAPI: 107. delete_message_safely(pending)<br/>(bot.py:325)
        end
        
        TelegramAPI->>TelegramAPI: 108. Bot.send_message() → Telegram API<br/>(aiogram Bot)
        TelegramAPI->>User: 109. Пользователь получает ответ<br/>+ кнопки 👍/👎
        deactivate TelegramAPI

    %% ═══════════════════════════════════════════════════════════
    %% АЛЬТЕРНАТИВНЫЕ ПУТИ И ОБРАБОТКА ОШИБОК
    %% ═══════════════════════════════════════════════════════════
    Note over BotCore: Обработка ошибок QA сервиса
    opt QAServiceTimeout
        BotCore->>BotCore: 110. "Поиск ответа занимает дольше..."<br/>(bot_service.py:191)
    end
    opt QAServiceUnavailable
        BotCore->>BotCore: 111. "Сервис временно недоступен..."<br/>(bot_service.py:197)
    end
    opt QAServiceError
        BotCore->>BotCore: 112. "Не удалось сформировать ответ..."<br/>(bot_service.py:203)
    end

    %% Обработка /start команды
    Note over BotCore: Обработка /start
    BotCore->>BotCore: 113. _build_start_buttons(is_subscribed)<br/>(bot_service.py:234)

    %% Callback обработка (подписка)
    Note over TelegramAPI,BotCore: Callback обработка
    TelegramAPI->>BotCore: 114. POST /callbacks<br/>(bot.py:222)
    BotCore->>BotCore: 115. BotService.handle_callback()<br/>(bot_service.py:43)
    BotCore->>Postgres: 116. UPDATE users SET is_subscribed = NOT is_subscribed
    Postgres-->>BotCore: 117. COMMIT
    BotCore-->>TelegramAPI: 118. BotResponse с новым статусом
end
```

---

### Детализация по каждому этапу

#### ЭТАП 1: Отправка вопроса пользователем (Platform Input)

**Участники:** Пользователь → Платформа (Telegram/VK/MAX)

**Описание:**
Пользователь отправляет текстовый вопрос через интерфейс мессенджера. Платформа генерирует событие `Message`.

**Реализация:**
- **Telegram**: `aiogram` Bot → Dispatcher → `handle_message()`
- **VK**: Аналогичный адаптер
- **MAX**: Go-сервис с аналогичной логикой

**Что происходит:**
1. Пользователь пишет вопрос: "Какие правила приёма в магистратуру?"
2. Платформа (Telegram Bot API / VK API / MAX API) получает событие `Message`
3. Адаптер определяет тип сообщения через `detect_message_type()`:
   - `text` — текстовое сообщение
   - `voice` — голосовое сообщение
   - `sticker`, `photo`, `video`, `audio`, `document` — медиа
4. Адаптер преобразует в единый формат через `_build_payload()`:

```python
{
    "platform": "telegram",
    "message_type": "text",
    "user_id": "123456789",
    "chat_id": "123456789",
    "text": "Какие правила приёма в магистратуру?",
    "message_id": "42",
    "timestamp": "2024-01-15T10:30:00Z",
    "metadata": {
        "username": "student",
        "first_name": "Иван",
        "last_name": "Иванов",
        "chat_type": "private"
    }
}
```

**Результат:**
- `IncomingMessage` — нормализованное сообщение

---

#### ЭТАП 2: Normalize и отправка в Bot-Core (Platform Adapter)

**Участники:** Platform Adapter → CoreClient

**Описание:**
Адаптер платформы отправляет нормализованное сообщение в bot-core через HTTP.

**Реализация (`bots/telegram/bot.py`):**
```python
class CoreClient:
    async def process_message(self, message: Message) -> dict[str, Any]:
        payload = self._build_payload(message)
        response = await self._client.post("/messages", json=payload)
        return response.json()
```

**Что происходит:**
1. `CoreClient.process_message()` отправляет POST запрос на `/messages`
2. Показывает "Ищу ответ на ваш вопрос..." (pending message) для текстовых сообщений кроме `/start` и `/ping`
3. Обрабатывает ошибки: HTTP 503, 500, таймауты

**Результат:**
- HTTP запрос к bot-core с нормализованным JSON

---

#### ЭТАП 3: Приём и маршрутизация в Bot-Core (API)

**Участники:** Bot-Core FastAPI → BotService

**Описание:**
Bot-Core принимает сообщение и передаёт в бизнес-логику.

**Реализация (`core/services/bot_service.py`):**
```python
def handle_message(self, message: IncomingMessage) -> BotResponse:
    user = self._user_service.upsert_user(message)
    
    if message.message_type == "text":
        return self._handle_text_message(message, user)
    if message.message_type == "voice":
        return self._handle_voice_message(message)
    return self._build_unsupported_message_response(message)
```

**Что происходит:**
1. Принимает POST на `/messages` с нормализованным JSON
2. Создаёт/обновляет пользователя через `UserService.upsert_user()`
3. Маршрутизирует по типу сообщения:
   - `text` → `_handle_text_message()`
   - `voice` → `_handle_voice_message()`
   - другие → `_build_unsupported_message_response()`

**UserService.upsert_user():**
```python
def upsert_user(self, message: IncomingMessage) -> User | None:
    # SELECT * FROM users WHERE platform = ? AND platform_user_id = ?
    user = session.query(User).filter(...).one_or_none()
    
    if user is None:
        # INSERT INTO users (...)
        user = User(platform=..., platform_user_id=...)
    else:
        # UPDATE users SET ...
        user.username = metadata.get("username")
    
    session.commit()
```

**Результат:**
- Пользователь сохранён/обновлён в БД
- Маршрутизация на обработчик

---

#### ЭТАП 4: Обработка текстового сообщения

**Участники:** BotService → QAServiceClient

**Описание:**
Обработка текстового сообщения, включая команды и вопросы к QA-сервису.

**Реализация (`_handle_text_message`):**
```python
def _handle_text_message(self, message: IncomingMessage, user) -> BotResponse:
    normalized_text = (message.text or "").strip()
    lowered_text = normalized_text.lower()

    if lowered_text == "/start":
        return self._build_start_response(message, user)
    if lowered_text == "/ping":
        reply_text = "pong"
    else:
        reply_text = self._ask_qa_service(normalized_text)

    return BotResponse(actions=[
        OutgoingAction(type=ActionType.send_text, text=reply_text,
                       buttons=self._build_feedback_buttons())
    ])
```

**Обрабатываемые команды:**
- `/start` — приветствие с inline кнопками "Начать новый диалог" и "Подписаться/Отписаться"
- `/ping` — возвращает "pong"
- любой другой текст → отправка в QA-сервис

**Голосовые сообщения (`_handle_voice_message`):**
```python
return BotResponse(actions=[
    OutgoingAction(
        type=ActionType.send_text,
        text="Я получил голосовое сообщение. Скоро здесь будет распознавание речи."
    )
])
```

**Результат:**
- Текст ответа для отправки пользователю
- Кнопки feedback (like/dislike) — **реализованы, но обработчики не подключены**

---

#### ЭТАП 5: Отправка в QA-Service (QAServiceClient)

**Участники:** QAServiceClient (Retry Logic)

**Описание:**
Клиент отправляет вопрос в QA-сервис с логикой повторных попыток.

**Реализация (`services/qa_service_client.py`):**
```python
class QAServiceClient:
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1.0
    MAX_BACKOFF = 8.0

    def ask(self, question: str, context: str | None = None) -> str:
        for attempt in range(self._max_retries):
            try:
                response = self._client.post("/qa", json={
                    "question": question,
                    "context": context,
                })
                
                # Retry на 503, 500, timeout, 429
                # ОбрабатываетConnectError
                
                response.raise_for_status()
                return response.json()["answer"]
            except Exception as e:
                # Логирование + backoff
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
        
        raise last_error
```

**Логика retry:**
- **503 (Unavailable)**: Exponential backoff, до 3 попыток
- **500 (Internal Error)**: Exponential backoff
- **429 (Rate Limited)**: Увеличенный backoff (x2)
- **Timeout**: Exponential backoff
- **Connect Error**: Exponential backoff

**Результат:**
- Ответ от QA-сервиса или исключение (`QAServiceTimeout`, `QAServiceUnavailable`, `QAServiceError`)

---

#### ЭТАП 6: Обработка вопроса в QA-Service (QA API)

**Участники:** QA FastAPI → LightRAG → Embedding → PGVector/PGGraph → LLM Pool

**Описание:**
QA-service получает вопрос и использует **LightRAG** как primary метод с fallback на **Classic RAG**.

**Реализация (`api/routes/qa.py`):**
```python
@router.post("", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """Основной endpoint: LightRAG (primary) + Classic RAG (fallback)."""
    use_lightrag = True  # Можно управлять через USE_LIGHT_RAG env var

    if use_lightrag:
        try:
            # Попытка LightRAG (timeout: 20s)
            result = await asyncio.wait_for(
                _query_lightrag(request.question),
                timeout=LIGHTRAG_TIMEOUT_SECONDS
            )
            return result
        except (asyncio.TimeoutError, Exception) as e:
            # Fallback на Classic RAG (timeout: 15s)
            return await asyncio.wait_for(
                _query_classic_rag(request.question),
                timeout=CLASSIC_RAG_TIMEOUT_SECONDS
            )
```

**Конфигурация:**

| Параметр | Значение | Описание |
|----------|----------|----------|
| LIGHTRAG_TIMEOUT_SECONDS | 20 | Timeout для LightRAG |
| CLASSIC_RAG_TIMEOUT_SECONDS | 15 | Timeout для Classic RAG fallback |

**LightRAG Query Flow:**

1. **Keyword extraction** - извлечение ключевых слов из вопроса
2. **Vector search** - поиск в PGVectorStorage (embedding similarity)
3. **Graph search** - поиск в PGGraphStorage (relations между сущностями)
4. **Full-text search** - дополнительный текстовый поиск
5. **Merge & Rank** - объединение и ранжирование результатов
6. **LLM generation** - генерация ответа через LLM Pool

**Storage:**

- **PGVectorStorage**: Хранение векторов (chunk_id → embedding)
- **PGGraphStorage**: Хранение графа знаний (entities + relations) - требует Apache AGE
- Fallback: **NetworkXStorage** если PGGraph недоступен

**Fallback логика:**

```
LightRAG (20s) → [timeout/error] → Classic RAG (15s) → [timeout/error] → Error Response
```

**Результат:**
- `QAResponse` с answer, model, sources

---

#### ЭТАП 7: Генерация эмбеддинга

**Участники:** Embedding Model (sentence-transformers)

**Описание:**
Текст вопроса преобразуется в 1024-мерный вектор для семантического поиска.

**Реализация (`kb/embedding.py`):**
```python
_model: Optional[SentenceTransformer] = None

def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        config = get_kb_config()
        _model = SentenceTransformer(config.embedding_model)  # deepvk/USER-bge-m3
    return _model

def get_embedding(text: str) -> list[float]:
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()  # 1024-мерный вектор
```

**Модель:** `deepvk/USER-bge-m3` (1024 dimensions)

**Результат:**
- Нормализованный вектор (list[float] длиной 1024)

---

#### ЭТАП 8: Векторный поиск в базе знаний

**Участники:** QA → PostgreSQL (pgvector)

**Описание:**
Выполняется семантический поиск по чанкам с использованием косинусного сходства pgvector.

**Реализация (`kb/search.py`):**
```python
async def search_chunks(
    query: str,
    embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    engine = get_engine()
    embedding_str = "[" + ",".join(map(str, embedding)) + "]"

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                c.id, 
                c.text, 
                c.title, 
                c.source_url,
                (e.embedding_vector <=> cast(:embedding as vector)) as similarity
            FROM chunks c
            JOIN embeddings e ON c.id = e.chunk_id
            WHERE e.embedding_vector IS NOT NULL
            ORDER BY e.embedding_vector <=> cast(:embedding as vector)
            LIMIT :top_k
        """), {"embedding": embedding_str, "top_k": top_k})

        chunks = []
        for row in result:
            chunks.append({
                "id": str(row.id),
                "text": row.text,
                "title": row.title,
                "source_url": row.source_url,
                "similarity": float(row.similarity),
            })

    return chunks
```

**SQL запрос:**
```sql
SELECT c.id, c.text, c.title, c.source_url,
       (e.embedding_vector <=> cast(:embedding as vector)) as similarity
FROM chunks c
JOIN embeddings e ON c.id = e.chunk_id
WHERE e.embedding_vector IS NOT NULL
ORDER BY e.embedding_vector <=> cast(:embedding as vector)
LIMIT 3;
```

**Оператор `<=>`**: Косинусное сходство pgvector

**Важно:** В коде используется `top_k=3`, а не 5 как в документации!

**Результат:**
- Список из 3 чанков с текстом, названием, source_url и similarity

---

#### ЭТАП 9: Построение контекста для LLM

**Участники:** QA (build_context_from_chunks)

**Описание:**
Из найденных чанков формируется контекст для промпта LLM.

**Реализация (`kb/search.py`):**
```python
def build_context_from_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return ""

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_url", "Unknown")
        title = chunk.get("title", "Untitled")
        text = chunk["text"]

        context_parts.append(
            f"--- Документ {i} ---\n"
            f"Источник: {source}\n"
            f"Название: {title}\n"
            f"Содержание: {text}\n"
        )

    return "\n\n".join(context_parts)
```

**Результат:**
- Текст контекста для LLM, например:
```
--- Документ 1 ---
Источник: https://abiturient.utmn.ru/magistr
Название: Правила приёма в магистратуру
Содержание: При приёме в магистратуру...
```

---

#### ЭТАП 10: Генерация ответа LLM Pool

**Участники:** LLM Pool → Mistral / GigaChat / OpenRouter

**Описание:**
Собранный промпт отправляется в LLM Pool с fallback логикой между провайдерами.

**Реализация (`llm/pool.py`):**
```python
class LLMPool:
    def __init__(self, config: LLMConfig | None = None):
        self._providers = {
            "mistral": MistralProvider(...),
            "openrouter": OpenRouterProvider(...),
            "gigaсhat": GigaChatProvider(...),
        }

    async def call(self, prompt: str, ...) -> LLMResponse:
        available = self.get_available_providers()
        providers_to_try = [p for p in self._config.model_priority if p in available]

        for prov_name in providers_to_try:
            provider = self._providers.get(prov_name)
            try:
                response = await provider.generate(prompt=prompt, ...)
                return response
            except Exception as e:
                continue  # Пробуем следующий провайдер

        raise ValueError("All providers failed")
```

**Промпт (config/prompts.py):**
```python
SYSTEM_PROMPT = """Ты — Виртуальный ассистент Тюменского государственного университета (ТюмГУ). 
Твоя задача — помогать студентам и абитуриентам с вопросами об университете.
Отвечай кратко и по существу. Если не знаешь ответ — честно скажи об этом.
Не называй себя ChatGPT, Claude или другой моделью. Ты — помощник ТюмГУ."""

SYSTEM_PROMPT_WITH_CONTEXT = """Ты — Виртуальный ассистент Тюменского государственного университета (ТюмГУ). 
Твоя задача — помогать студентам и абитуриентам с вопросами об университете.
Отвечай кратко и по существу. Если не знаешь ответ — честно скажи об этом.
Не называй себя ChatGPT, Claude или другой моделью. Ты — помощник ТюмГУ.

При ответе на вопрос ИСПОЛЬЗУЙ ТОЛЬКО информацию из предоставленного контекста.
Не добавляй информацию, которой нет в контексте.
Если в контексте недостаточно информации — скажи об этом."""
```

**Fallback порядок:** Mistral → GigaChat → OpenRouter (по умолчанию)

**Результат:**
- `LLMResponse` с content, model, usage

---

#### ЭТАП 11: Формирование ответа пользователю

**Участники:** BotService → Platform Adapter → Пользователь

**Описание:**
Формируется итоговый ответ и отправляется через платформу.

**Реализация:**
```python
# В qa_service_client.ask()
return payload["answer"]  # Просто текст ответа

# В bot_service._handle_text_message()
reply_text = self._ask_qa_service(normalized_text)

return BotResponse(actions=[
    OutgoingAction(
        type=ActionType.send_text,
        text=reply_text,
        buttons=self._build_feedback_buttons(),
    )
])
```

**Platform adapter:**
```python
# bots/telegram/bot.py
for action in bot_response.get("actions", []):
    if action.get("type") == "send_text" and action.get("text"):
        await message.answer(
            action["text"],
            reply_markup=build_inline_keyboard(action.get("buttons", [])),
        )
```

**Кнопки feedback:**
```python
def _build_feedback_buttons(self) -> list[list[InlineButton]]:
    return [
        [
            InlineButton(text="👍", callback_data="feedback:like"),
            InlineButton(text="👎", callback_data="feedback:dislike"),
        ]
    ]
```

**Важно:** Кнопки создаются, но обработчики `feedback:like` и `feedback:dislike` **не реализованы** в `handle_callback()`.

**Результат:**
- Пользователь получает ответ с кнопками 👍/👎

---

## Что реализовано vs Что в документации

| Компонент | В коде | В документации |
|-----------|--------|----------------|
| LightRAG (primary) | ✅ Есть | ✅ Обновлено |
| Classic RAG (fallback) | ✅ Есть | ✅ Обновлено |
| `/qa` endpoint | ✅ LightRAG + fallback | ✅ Обновлено |
| `/qa/lightrag` endpoint | ✅ Есть | ✅ Обновлено |
| `/qa/classic` endpoint | ✅ Есть | ✅ Обновлено |
| Knowledge Graph (PGGraphStorage) | ✅ Есть | ✅ Обновлено |
| `/qa/categorize` endpoint | ❌ Нет | ❌ Устарело |
| Категоризация вопроса (greeting/kb_query/clarification) | ❌ Нет | ❌ Устарело |
| Session/History management | ❌ Нет | ❌ Устарело |
| Логирование вопросов-ответов в БД | ❌ Нет | ❌ Устарело |
| Feedback обработка (like/dislike) | ⚠️ Кнопки есть, обработка нет | ⚠️ Частично |
| top_k для поиска | 3 | ✅ 3 |
| STT для голосовых | ⚠️ Заглушка | ⚠️ Заглушка |

---

## Таблицы базы данных

| Таблица | Назначение |
|---------|------------|
| `users` | Пользователи платформ (platform, platform_user_id, username, first_name, last_name, is_subscribed) |
| `subscriptions` | История подписок (user_id, subscribed_at, unsubscribed_at) |
| `chunks` | Текстовые чанки из документов (text, title, source_url) |
| `embeddings` | Векторные представления чанков (chunk_id, embedding_vector) |
| `holidays` | Праздники для рассылки |

---

## API Endpoints

### Bot-Core

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | /messages | Приём нормализованных сообщений |
| POST | /callbacks | Приём callback событий |
| GET | /health | Проверка здоровья |

### QA-Service

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | /qa | **LightRAG (primary) + Classic RAG (fallback)** |
| POST | /qa/lightrag | Только LightRAG |
| POST | /qa/classic | Только Classic RAG |
| GET | /health | Проверка здоровья |
| GET | /kb/chunks | Просмотр чанков |
| GET | /kb/chunks/count | Количество чанков |
| POST | /kb/import-to-lightrag | Импорт чанков в LightRAG |
| POST | /kb/rebuild-knowledge-graph | Перестроение графа знаний |
| GET | /kb/index-status | Статус индекса LightRAG |
| GET | /kb/index-versions | История версий индекса |

---

## Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3.12, FastAPI |
| Bot Framework | aiogram 3.x (Telegram), vkbottle (VK) |
| Database | PostgreSQL 18 + pgvector + Apache AGE |
| Embeddings | deepvk/USER-bge-m3 (1024 dimensions) |
| RAG | LightRAG (Hybrid: vector + graph + fulltext) + Classic RAG fallback |
| LLM Pool | Mistral → GigaChat → OpenRouter |
| Vector Storage | PGVectorStorage (PostgreSQL) |
| Graph Storage | PGGraphStorage (Apache AGE) / NetworkXStorage (fallback) |
| Containerization | Docker, Docker Compose |
| Docker Image | dawsonlp/postgres-batteries-inc |

---

## Жизненный цикл запроса (Timeline)

```
Время    | Компонент       | Действие
---------|-----------------|----------------------------------
0ms      | Пользователь    | Отправляет вопрос в Telegram
10ms     | Telegram Adapter| normalize_message() → IncomingMessage
20ms     | CoreClient      | POST /messages → bot-core
30ms     | BotCore API     | Принимает POST /messages
40ms     | BotService      | handle_message()
50ms     | UserService     | upsert_user() → users table
60ms     | BotService      | _handle_text_message()
70ms     | QAServiceClient | POST /qa → qa-service (с retry)
80ms     | QA API          | ask_question() → LightRAG
90ms     | LightRAG        | aquery(question, mode="mix")
100ms    | Embedding       | get_embedding() → 1024-vector
110ms    | PGVector        | Vector search (top_k)
120ms    | PGGraph         | Graph search (entities + relations)
130ms    | LightRAG        | merge_and_rank(results)
140ms    | LLM Pool        | select_model() → Mistral
160ms    | Mistral API     | response JSON
170ms    | QA Service      | Формирует QAResponse
180ms    | QAServiceClient | Возвращает answer
190ms    | BotService      | Формирует BotResponse
200ms    | Telegram Adapter| sendMessage с кнопками
210ms    | Пользователь    | Получает ответ

Примечание: При LightRAG timeout/error → fallback на Classic RAG (+15s)
```

---

## Особенности реализации

### Обработка ошибок QA-Service

```python
def _ask_qa_service(self, question: str) -> str:
    try:
        return self._qa_service_client.ask(question=question)
    except QAServiceTimeout:
        return "Поиск ответа занимает дольше обычного. Попробуйте переформулировать вопрос."
    except QAServiceUnavailable:
        return "Сервис временно недоступен. Мы уже работаем над устранением проблемы."
    except QAServiceError:
        return "Не удалось сформировать ответ. Попробуйте переформулировать вопрос."
    except Exception:
        return "Что-то пошло не так. Попробуйте повторить запрос позже."
```

### Retry логика

- Максимум 3 попытки
- Exponential backoff: 1s → 2s → 4s → 8s (max)
- Rate limited (429): удвоенный backoff

### Инициализация при старте

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload embedding model
    get_embedding_model()
    
    # Инициализация LLM Pool
    llm_pool = get_llm_pool()
    available = llm_pool.get_available_providers()
    
    # Опционально LightRAG
    if os.getenv("USE_LIGHT_RAG") == "true":
        await init_lightrag()
    
    yield
    # Shutdown
```

---

## Технологический стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3.12, FastAPI |
| Bot Framework | aiogram 3.x (Telegram), vkbottle (VK) |
| Database | PostgreSQL 18 + pgvector + Apache AGE |
| Embeddings | deepvk/USER-bge-m3 (1024 dimensions) |
| RAG | LightRAG (Hybrid) + Classic RAG fallback |
| LLM Pool | Mistral → GigaChat → OpenRouter |
| Containerization | Docker, Docker Compose |
| Docker Image | dawsonlp/postgres-batteries-inc |
