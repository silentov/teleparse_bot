# Архитектура проекта

## 1. Назначение системы

Система получает от пользователя Telegram username канала, читает последние сообщения этого канала и формирует краткую текстовую сводку через LLM.

С архитектурной точки зрения это небольшой asynchronous application с четырьмя главными зонами ответственности:

1. Telegram UI и маршрутизация пользовательских действий;
2. чтение сообщений канала через userbot;
3. хранение пользовательского контекста и сериализация доступа через Redis;
4. генерация LLM-summary.

## 2. Упрощённая схема компонентов

```text
Пользователь Telegram
        |
        v
 MainBot (Telethon Bot API client)
        |
        +--> RedisFSMDispatcher --> FSM --> RedisService / LockService --> Redis
        |
        +--> UserBot (Telethon user client) --> Telegram channel history
        |
        +--> LLMProvider --> LangChain --> DeepSeek-compatible chat model
```

## 3. Главные модули

### 3.1. Bootstrap

Файл: `src/main.py`

Отвечает за:

- настройку логирования;
- загрузку конфигурации;
- создание Redis-менеджера;
- создание Telegram-клиентов;
- создание FSM, dispatcher и LLMProvider;
- запуск `MainBot`.

### 3.2. Telegram-слой

Каталог: `src/bot/`

#### `bot_client.py`

Класс `MainBot`:

- принимает входящие сообщения и callback-и;
- регистрирует обработчики Telethon;
- управляет пользовательским сценарием;
- запускает парсинг канала и отправку результата;
- делает graceful shutdown клиентов.

#### `userbot_client.py`

Класс `UserBot`:

- один раз стартует пользовательскую сессию;
- разрешает username канала через `get_entity`;
- забирает историю через `get_messages`;
- конвертирует сообщения в DTO для LLM-слоя.

#### `keyboards.py`, `texts/`

Содержат UI-артефакты:

- inline-кнопки;
- константные тексты;
- форматирование сообщений, которые бот отправляет/редактирует.

## 4. FSM и маршрутизация

Каталог: `src/fsm/`

### `FSM`

Отвечает за:

- чтение и запись контекста пользователя в Redis;
- переключение состояний;
- обновление произвольных данных контекста;
- сброс FSM в состояние по умолчанию.

### `RedisFSMDispatcher`

Отвечает за:

- маршрутизацию `NewMessage` по команде или текущему состоянию;
- маршрутизацию `CallbackQuery` по точному `callback_data` или по префиксу;
- сериализацию обработки через redis-lock на пару `(chat_id, user_id)`.

### Актуальные состояния FSM

Файл: `src/fsm/fsm_states.py`

| Состояние | Назначение |
|---|---|
| `default` | нейтральное состояние |
| `wait_channel` | бот ждёт username канала |
| `wait_limit` | бот ждёт нажатия inline-кнопки с лимитом |
| `wait_custom_limit` | бот ждёт ручной ввод числа |

Дополнительно в enum присутствует `wait_parse_start`, но в текущем runtime не используется.

## 5. Redis-слой

Каталог: `src/infrastructure/redis/`

### `RedisManager`

- поднимает connection pool;
- проверяет доступность Redis через `PING`;
- закрывает соединения при остановке.

### `RedisService`

- даёт базовые операции `get/set` и JSON-сериализацию;
- хранит FSM-контекст в Redis hash;
- обновляет TTL контекста.

### `LockService` и `RedisLock`

- создают распределённые локи;
- используют `SET NX PX`;
- освобождают/продлевают лок через Lua-скрипты.

## 6. LLM-слой

Каталог: `src/llm/`

### `LLMProvider`

- создаёт chat model через `langchain.chat_models.init_chat_model`;
- оборачивает модель в `with_structured_output(StructuredMessage)`;
- отправляет асинхронный запрос через `ainvoke`;
- валидирует структурированный ответ и нормализует его до `LLMSummaryResult`.

### DTO и схемы

Файл: `src/llm/schema.py`

- `TelegramMessageDTO` — минимальный контракт сообщения для внутренних слоёв;
- `ChannelMessagesResult` — результат чтения канала;
- `StructuredMessage` — ожидаемая структура ответа LLM;
- `LLMSummaryResult` — нормализованный результат для приложения.

## 7. Поток основного пользовательского сценария

```text
/start
  -> MainBot.start_handler
  -> FSM reset
  -> главное меню

Нажатие «Получить посты»
  -> callback_get_messages
  -> state = wait_channel

Ввод username канала
  -> get_messages_limit
  -> ctx.data.channel = <username>
  -> state = wait_limit

Выбор лимита / ручной ввод
  -> callback_limit или get_messages_custom_limit
  -> _parse_and_send
  -> UserBot.get_messages
  -> LLMProvider.send_message
  -> редактирование сообщения бота итоговой сводкой
  -> FSM reset
```

## 8. Границы ответственности

Текущая архитектура в целом соблюдает полезные разделения:

- `bot/` — UI, доставка и orchestration;
- `fsm/` — состояние диалога и маршрутизация;
- `infrastructure/redis/` — техническая интеграция с Redis;
- `llm/` — интеграция с моделью и контракт результата.

Это разделение важно сохранять дальше: не смешивать Telegram UI, Redis-хранилище и LLM-логику в одном модуле.