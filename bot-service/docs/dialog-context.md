# Контекст Диалога

Контекст диалога реализован в `bot-core`, а не в `qa-service`.

## Где хранится

Используются таблицы:

- `sessions` — активный диалог пользователя
- `messages` — история внутри диалога
- `questions_answers` — связка вопроса и ответа

## Как это работает

При новом обычном текстовом сообщении:

1. `bot-core` находит или создает активную сессию пользователя.
2. Берет последние сообщения из этой сессии.
3. Собирает их в текстовый контекст.
4. Добавляет к текущему вопросу.
5. Отправляет запрос в `qa-service`.
6. Сохраняет вопрос и ответ в БД.

## Трассировка По Функциям

1. `core/services/bot_service.py -> _handle_dialog_message()`
2. `core/services/dialog_service.py -> get_or_create_active_session()`
3. `core/services/dialog_service.py -> build_context()`
4. `core/services/bot_service.py -> _build_qa_question()`
5. `core/services/bot_service.py -> _ask_qa_service()`
6. `core/services/qa_service_client.py -> ask()`
7. `core/services/dialog_service.py -> save_question_answer()`

При сохранении пары вопрос-ответ внутри `save_question_answer()` вызываются:

1. создание `DialogMessage` с ролью `user`
2. создание `DialogMessage` с ролью `assistant`
3. создание `QuestionAnswerLink`
4. обновление `sessions.last_message_at`

## Лимит контекста

Используется переменная:

- `DIALOG_CONTEXT_LIMIT_MESSAGES`

Текущее значение по умолчанию:

- `7`

Это лимит последних сообщений, которые попадают в контекст.

## Новый диалог

Кнопка `Начать новый диалог`:

- закрывает активную сессию переводом ее в состояние `CLOSED`
- создает новую сессию со state `DIALOG`

Старая история не удаляется и остается в БД.

### Трассировка кнопки нового диалога

1. Адаптер отправляет callback `dialog:start_new`
2. `core/services/bot_service.py -> handle_callback()`
3. `core/services/user_service.py -> get_user()`
4. `core/services/dialog_service.py -> start_new_dialog()`

## Что не сохраняется

В историю не пишутся:

- `/start`
- `/ping`
- другие служебные slash-команды
- неподдерживаемые форматы сообщений
- заглушки по голосовым сообщениям
