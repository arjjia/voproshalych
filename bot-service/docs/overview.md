# Обзор Сервиса

`bot-service` разделен на общий `bot-core` и платформенные адаптеры.

## Состав

- `core/main.py` — FastAPI приложение `bot-core`
- `core/services/bot_service.py` — основная бизнес-логика
- `core/services/user_service.py` — сохранение пользователей и подписок
- `core/services/dialog_service.py` — сессии диалога и история сообщений
- `core/services/qa_service_client.py` — клиент к `qa-service`
- `core/services/holiday_newsletter.py` — праздничная рассылка

## Что умеет `bot-core`

- принимает нормализованные сообщения от Telegram, VK и MAX
- сохраняет пользователя в БД
- обрабатывает `/start` и `/ping`
- поддерживает inline callback-кнопки
- хранит историю диалога
- собирает контекст для QA из последних сообщений
- запускает праздничную рассылку вручную и по расписанию

## Трассировка По Функциям

### Обработка сообщения

1. `core/main.py -> process_message()`
2. `core/services/bot_service.py -> BotService.handle_message()`
3. `core/services/user_service.py -> UserService.upsert_user()`
4. `core/services/bot_service.py -> _handle_text_message()`
5. `core/services/bot_service.py -> _handle_dialog_message()`
6. `core/services/dialog_service.py -> get_or_create_active_session()`
7. `core/services/dialog_service.py -> build_context()`
8. `core/services/bot_service.py -> _build_qa_question()`
9. `core/services/bot_service.py -> _ask_qa_service()`
10. `core/services/qa_service_client.py -> QAServiceClient.ask()`
11. `core/services/dialog_service.py -> save_question_answer()`

### Обработка callback

1. `core/main.py -> process_callback()`
2. `core/services/bot_service.py -> BotService.handle_callback()`
3. `core/services/user_service.py -> toggle_subscription()`
4. или `core/services/dialog_service.py -> start_new_dialog()`

### Праздничная рассылка

1. `core/main.py -> send_today_holiday_newsletter()`
2. `core/services/bot_service.py -> send_today_holiday_newsletter()`
3. `core/services/holiday_newsletter.py -> send_today_newsletter()`
4. `core/services/holiday_newsletter.py -> get_today_holiday()`
5. `core/services/holiday_newsletter.py -> get_subscribed_users()`
6. `core/services/holiday_newsletter.py -> _build_newsletter_key()`
7. `core/services/holiday_newsletter.py -> _acquire_newsletter_lock()`
8. `core/services/qa_service_client.py -> generate_holiday_greeting()`
9. `core/services/holiday_newsletter.py -> _get_sent_recipient_keys()`
10. `core/services/holiday_newsletter.py -> _send_to_user()`
11. для `MAX`: `max-bot -> /internal/send -> handleInternalSend() -> sendMessage()`
12. `core/services/holiday_newsletter.py -> _mark_delivery_sent()`
13. `core/services/holiday_newsletter.py -> _mark_summary()`

## Платформенные адаптеры

- Telegram: отправка текста, inline-кнопки, callback, временное сообщение ожидания
- VK: отправка текста, inline-кнопки, временное сообщение ожидания
- MAX: отправка текста, inline-кнопок и внутренний endpoint для рассылки

## База данных

`bot-core` использует уже существующие таблицы:

- `users`
- `subscriptions`
- `sessions`
- `messages`
- `questions_answers`
- `holidays`
- `telemetry_logs`

## Ключевые ограничения

- `context` в `qa-service` не используется как память диалога
- контекст диалога собирается только в `bot-core`
- для `MAX` рассылка идет через внутренний endpoint адаптера, а не напрямую из `bot-core`
