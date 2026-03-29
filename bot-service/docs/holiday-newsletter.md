# Праздничная Рассылка

Праздничная рассылка работает в `bot-core`.

## Что используется

Таблицы:

- `holidays` — источник праздников
- `users` — пользователи платформ
- `subscriptions` — история подписок
- `telemetry_logs` — защита от повторной отправки в тот же день

Сервисы:

- `core/services/holiday_newsletter.py`
- `core/services/qa_service_client.py`
- `qa-service` endpoint `POST /qa/holiday`
- `max-bot` внутренний endpoint `POST /internal/send`

## Как работает

1. `bot-core` ищет праздник на текущую дату в `holidays`.
2. Выбирает пользователей с `users.is_subscribed = true`.
3. Запрашивает текст поздравления в `qa-service`.
4. Берет advisory lock на конкретную рассылку за день.
5. Отправляет поздравление только тем подписчикам, которым оно еще не доставлялось.
6. Пишет per-user delivery лог и итоговую сводку в `telemetry_logs`.

Для `MAX` отправка идет не напрямую из `bot-core`, а через внутренний HTTP endpoint адаптера `max-bot`.

## Трассировка По Функциям

### Ручной запуск

1. `core/main.py -> send_today_holiday_newsletter()`
2. `core/services/bot_service.py -> send_today_holiday_newsletter()`
3. `core/services/holiday_newsletter.py -> send_today_newsletter()`

### Ежедневный фоновый запуск

1. `core/main.py -> lifespan()`
2. `core/main.py -> _holiday_newsletter_loop()`
3. `core/main.py -> bot_service.send_today_holiday_newsletter()`

### Внутренний поток рассылки

1. `core/services/holiday_newsletter.py -> get_today_holiday()`
2. `core/services/holiday_newsletter.py -> get_subscribed_users()`
3. `core/services/holiday_newsletter.py -> _build_newsletter_key()`
4. `core/services/holiday_newsletter.py -> _acquire_newsletter_lock()`
5. `core/services/qa_service_client.py -> generate_holiday_greeting()`
6. `qa-service -> /qa/holiday`
7. `core/services/holiday_newsletter.py -> _get_sent_recipient_keys()`
8. `core/services/holiday_newsletter.py -> _send_to_user()`
9. `core/services/holiday_newsletter.py -> _send_telegram_message()` или `_send_vk_message()` или `_send_max_message()`
10. `max-bot -> /internal/send`
11. `bots/max/main.go -> handleInternalSend()`
12. `bots/max/main.go -> sendMessage()`
13. `core/services/holiday_newsletter.py -> _mark_delivery_sent()`
14. `core/services/holiday_newsletter.py -> _mark_summary()`
15. `core/services/holiday_newsletter.py -> _release_newsletter_lock()`

## Когда запускается

Есть два режима:

- вручную через `POST /newsletters/holidays/send-today`
- автоматически фоновым циклом внутри `bot-core`

Настройки:

- `HOLIDAY_NEWSLETTER_ENABLED`
- `HOLIDAY_NEWSLETTER_RUN_HOUR`
- `HOLIDAY_NEWSLETTER_RUN_MINUTE`

## Что уже поддержано

- Telegram
- VK
- MAX через внутренний endpoint `max-bot`

## Что нужно для работы

Достаточно:

1. заполнить таблицу `holidays`
2. иметь подписанных пользователей
3. поднять `qa-service` и `bot-core`
4. поднять `max-bot`, если нужна рассылка в MAX

После этого рассылка может выполняться автоматически по расписанию.
