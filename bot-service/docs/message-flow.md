# Путь Сообщения

## Общий поток

1. Пользователь пишет в Telegram, VK или MAX.
2. Адаптер платформы нормализует update в `IncomingMessage`.
3. Адаптер вызывает `POST /messages` в `bot-core`.
4. `bot-core` сохраняет пользователя.
5. Для обычного текста `bot-core` получает активную сессию диалога.
6. `bot-core` собирает контекст из последних сообщений.
7. `bot-core` вызывает `qa-service`.
8. Ответ сохраняется в историю и возвращается адаптеру.
9. Адаптер отправляет ответ пользователю.

## Трассировка По Функциям

### Telegram

1. `bots/telegram/bot.py -> build_dispatcher()`
2. `bots/telegram/bot.py -> handle_message()`
3. `bots/telegram/bot.py -> CoreClient.process_message()`
4. `bots/telegram/bot.py -> CoreClient._build_payload()`
5. `core/main.py -> process_message()`
6. `core/services/bot_service.py -> handle_message()`
7. `core/services/bot_service.py -> _handle_text_message()` или `_handle_voice_message()`
8. `bots/telegram/bot.py -> build_inline_keyboard()`
9. `bots/telegram/bot.py -> message.answer()`

### VK

1. `bots/vk/bot.py -> build_bot()`
2. `bots/vk/bot.py -> handle_message()`
3. `bots/vk/bot.py -> CoreClient.process_message()`
4. `bots/vk/bot.py -> CoreClient._build_payload()`
5. `core/main.py -> process_message()`
6. `core/services/bot_service.py -> handle_message()`
7. `bots/vk/bot.py -> build_inline_keyboard()`
8. `bots/vk/bot.py -> message.answer()`

### VK callback

1. `bots/vk/bot.py -> handle_callback()`
2. `bots/vk/bot.py -> build_callback_payload()`
3. `bots/vk/bot.py -> CoreClient.process_callback()`
4. `core/main.py -> process_callback()`
5. `core/services/bot_service.py -> handle_callback()`
6. `bots/vk/bot.py -> bot.api.messages.send()` или `send_message_event_answer()`

### MAX

1. `bots/max/main.go -> main()`
2. `bots/max/main.go -> handleUpdate()`
3. `bots/max/main.go -> buildIncomingMessage()`
4. `bots/max/main.go -> CoreClient.ProcessMessage()`
5. `core/main.py -> process_message()`
6. `core/services/bot_service.py -> handle_message()`
7. `bots/max/main.go -> addKeyboardToMessage()`
8. `bots/max/main.go -> api.Messages.Send()`

### MAX callback

1. `bots/max/main.go -> handleUpdate()`
2. `bots/max/main.go -> handleCallbackUpdate()`
3. `bots/max/main.go -> buildCallbackEvent()`
4. `bots/max/main.go -> CoreClient.ProcessCallback()`
5. `core/main.py -> process_callback()`
6. `core/services/bot_service.py -> handle_callback()`
7. `bots/max/main.go -> sendMessage()`

## Входная модель

`core/models/message.py`

Основные поля:

- `platform`
- `message_type`
- `user_id`
- `chat_id`
- `text`
- `message_id`
- `timestamp`
- `metadata`

## Callback-поток

1. Пользователь нажимает inline-кнопку.
2. Адаптер формирует `CallbackEvent`.
3. Адаптер вызывает `POST /callbacks`.
4. `bot-core` обрабатывает действие.

Сейчас через callback работают:

- `subscription:toggle`
- `dialog:start_new`

### Трассировка callback

1. Платформа формирует callback update
2. Адаптер вызывает `POST /callbacks`
3. `core/main.py -> process_callback()`
4. `core/services/bot_service.py -> handle_callback()`
5. `core/services/user_service.py -> toggle_subscription()` или
6. `core/services/dialog_service.py -> start_new_dialog()`

## Сервисные сценарии

В историю не попадают:

- `/start`
- `/ping`
- другие slash-команды
- неподдерживаемые типы сообщений
- голосовые сообщения до подключения STT
- callback-события
