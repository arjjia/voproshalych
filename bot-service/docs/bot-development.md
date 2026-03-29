# Bot Service Docs

Краткая документация по `bot-service`.

Файлы:

- `overview.md` — состав сервиса и ключевые точки входа
- `message-flow.md` — путь сообщения от платформы до ответа
- `dialog-context.md` — как хранится и используется контекст диалога
- `holiday-newsletter.md` — как работает праздничная рассылка

Ключевые директории:

- `core` — общая бизнес-логика, работа с БД, контекстом и рассылкой
- `bots/telegram` — адаптер Telegram на `aiogram`
- `bots/vk` — адаптер VK на `vkbottle`
- `bots/max` — адаптер MAX на Go

Основные HTTP endpoints `bot-core`:

- `GET /health`
- `POST /messages`
- `POST /callbacks`
- `POST /newsletters/holidays/send-today`

Внутренний endpoint адаптера `MAX`:

- `POST /internal/send` в `max-bot`

Трассировка по темам вынесена в отдельные файлы:

- `message-flow.md` — трассер сообщения и callback
- `dialog-context.md` — трассер контекста диалога
- `holiday-newsletter.md` — трассер праздничной рассылки
