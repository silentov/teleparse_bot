# Runtime-поведение приложения

## 1. Общий жизненный цикл

Функция `main()` в `src/main.py` делает следующее:

1. определяет `APP_ENV` для логгера;
2. настраивает `loguru`;
3. загружает настройки через `get_settings()`;
4. создаёт и запускает `RedisManager`;
5. создаёт `RedisService` и `LockService`;
6. создаёт `LLMProvider`;
7. создаёт два `TelegramClient`:
   - `bot_session`
   - `async_session`
8. создаёт `FSM` и `RedisFSMDispatcher`;
9. создаёт `MainBot` и запускает `await bot.run()`.

## 2. Как стартует `MainBot`

В `MainBot.run()` происходит:

1. регистрация signal handlers, если платформа это поддерживает;
2. запуск bot-клиента через `start(bot_token=...)`;
3. запуск userbot-клиента через `UserBot.start()`;
4. блокирующее ожидание `run_until_disconnected()`.

Пока Telethon не отключён, приложение остаётся в рабочем состоянии и принимает апдейты.

## 3. Поведение Telethon, подтверждённое документацией

Через Context7 проверено следующее:

- `TelegramClient.start(...)` — стандартный путь инициализации клиента;
- `run_until_disconnected()` удерживает клиент активным, пока соединение не будет закрыто;
- обработчики событий Telethon должны быть `async def`;
- `events.CallbackQuery` предназначен для обработки inline callback-ов;
- `get_entity()` и `get_messages()` используются как стандартный способ разрешить сущность и получить историю сообщений.

## 4. Маршрутизация входящих событий

### 4.1. Новые сообщения

Все `events.NewMessage(incoming=True)` идут в `MainBot.on_message()`, а затем в `RedisFSMDispatcher.dispatch()`.

Диспетчер:

1. получает `chat_id` и `user_id`;
2. берёт **короткий** redis-lock на пару `(chat_id, user_id)` только для чтения контекста и выбора маршрута;
3. если текст начинается с `/`, ищет command-handler, а при отсутствии — `unknown_command`;
4. иначе ищет handler текущего состояния;
5. для хендлеров, помеченных `run_outside_lock`, ставит флаг `fsm:processing:<chat_id>:<user_id>` и выполняет долгую работу вне lock;
6. при параллельном конфликте отвечает через `contention`-handler контролируемым сообщением пользователю;
7. для коротких хендлеров повторно берёт короткий lock перед фактическим вызовом.

### 4.2. Callback-и

Все `events.CallbackQuery()` идут в `MainBot.on_callback()`, а затем в `dispatch_callback()`.

Алгоритм:

1. декодируется `event.data`;
2. берётся короткий redis-lock на пользователя для выбора callback-handler;
3. сначала ищется точное совпадение `callback_data`;
4. если его нет — ищется handler по префиксу.

Именно так обрабатывается группа callback-ов `limit:*`.

## 5. Что хранится в FSM

FSM-контекст хранится в Redis hash по ключу:

```text
fsm:<chat_id>:<user_id>
```

Поля hash:

- `state`
- `data`
- `updated_at`

`data` сериализуется через `orjson`.

## 6. TTL и сериализация доступа

### FSM TTL

По умолчанию TTL FSM-контекста — `1800` секунд.

TTL обновляется:

- при чтении контекста через `get_fsm_context(..., touch_ttl_sec=...)`;
- при записи state;
- при записи data.

### Локи

Лок для FSM создаётся по ключу:

```text
lock:fsm:<chat_id>:<user_id>
```

Dispatcher использует TTL `20000 ms`, чтобы не дать нескольким событиям одного пользователя одновременно повредить FSM-контекст.

В текущей реализации lock-критические секции укорочены до `5000 ms`, а долгие Telegram/LLM операции запускаются вне lock под отдельным флагом обработки пользователя.

## 7. Что происходит в основном happy path

1. пользователь нажимает `Получить посты`;
2. bot редактирует сообщение и переводит пользователя в `wait_channel`;
3. пользователь вводит username канала;
4. bot сохраняет `channel` и `bot_message_id`, затем переводит состояние в `wait_limit`;
5. пользователь выбирает лимит кнопками или вводит число вручную;
6. `_parse_and_send()` показывает текст загрузки;
7. `UserBot.get_messages()` читает канал;
8. `LLMProvider.send_message()` формирует summary;
9. bot редактирует исходное сообщение итогом и кнопками действий;
10. FSM сбрасывается в `default`.

Если в `wait_limit` приходит обычный текст, бот не пытается интерпретировать его как лимит и отправляет инструкцию выбрать значение кнопкой.

## 7.1. Поведение команд в любом состоянии

- `/start` — сброс FSM и возврат в главное меню;
- `/cancel` — принудительная отмена текущего сценария и сброс FSM;
- `/help` — показ справки;
- неизвестные slash-команды (`/foo`) не попадают в state-handler и обрабатываются отдельным controlled-response.

## 8. Логирование

Логгер настроен в `src/app_logger.py`.

Сейчас в `main.py` он запускается с параметрами:

- `log_json=False`
- `log_to_file=True`
- `intercept_std_logging=True`

Итог:

- лог идёт в stderr;
- пишется `src/logs/app.log`;
- пишется `src/logs/error.log`;
- `app.jsonl` **не создаётся**, пока `log_json=False`.

## 9. Обработка ошибок

В `_parse_and_send()` отдельно обрабатываются:

- `InvalidUserInputError`
- `TelegramAccessError`
- `LLMProviderError`
- `AppError`
- все прочие `Exception`

Во всех случаях пользователю отправляется/редактируется сообщение с `error_text(error)`, а FSM сбрасывается.

Особенность: текст ошибки в текущем UI фактически пробрасывается пользователю напрямую.

## 10. Graceful shutdown

`MainBot._shutdown()` делает:

1. `await self._userbot.stop()`;
2. `await self._client.disconnect()`, если bot-клиент ещё подключён.

`main()` в `finally` затем всегда вызывает:

```python
await redis_manager.stop()
```

То есть Redis закрывается на уровне bootstrap, а Telegram-клиенты — на уровне `MainBot`.

## 11. Важные операционные нюансы

- на Windows `loop.add_signal_handler()` может быть недоступен; это уже учтено через `except NotImplementedError`;
- userbot стартует один раз и переиспользуется, а не открывает новое соединение на каждый запрос;
- повторных попыток подключения к Redis на уровне `RedisManager.start()` сейчас нет;
- специальных обработчиков `FloodWait`, rate limits и backoff для Telegram API пока нет;
- file-логи внутри контейнера не вынесены в volume, поэтому при пересоздании контейнера они не считаются устойчивым источником истории.