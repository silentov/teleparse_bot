from __future__ import annotations

from telethon import events
from typing import Awaitable, Callable

from redis_fsm import RedisFSM, FSMContext

StateHandler = Callable[[events.NewMessage.Event, FSMContext], Awaitable[None]]
CallbackHandler = Callable[[events.CallbackQuery.Event, FSMContext], Awaitable[None]]


class RedisFSMDispatcher:
    def __init__(self, fsm: RedisFSM):
        self.fsm = fsm
        self.handlers: dict[str, Callable[..., Awaitable[None]]] = {}
        self.callback_handlers: dict[str, Callable[..., Awaitable[None]]] = {}

    def handler(self, state: str):
        def deco(fn: StateHandler):
            self.handlers[state] = fn
            return fn

        return deco

    def callback_handler(self, callback_data: str):
        """Декоратор для регистрации callback-хендлеров."""

        def deco(fn: CallbackHandler):
            self.callback_handlers[callback_data] = fn
            return fn

        return deco

    async def dispatch(self, event: events.NewMessage.Event) -> None:
        chat_id = event.chat_id
        user_id = event.sender_id
        if chat_id is None or user_id is None:
            return

        key = (chat_id, user_id)

        # сериализация по ключу (важно для корректной FSM)
        async with self.fsm.lock(key, ttl_ms=20000):
            ctx = await self.fsm.get_ctx(key)

            # Проверяем команды (начинаются с /)
            text = (event.raw_text or "").strip()
            if text.startswith("/"):
                handler = self.handlers.get(text)
                if handler:
                    await handler(event, ctx)
                    return

            # Иначе используем хендлер для текущего состояния
            handler = self.handlers.get(ctx.state) or self.handlers.get("default")
            if handler is None:
                return

            await handler(event, ctx)

    async def dispatch_callback(self, event: events.CallbackQuery.Event) -> None:
        """Обработка callback-запросов от inline-кнопок."""
        chat_id = event.chat_id
        user_id = event.sender_id
        if chat_id is None or user_id is None:
            return

        key = (chat_id, user_id)

        # Получаем данные из callback
        callback_data = (
            event.data.decode("utf-8") if isinstance(event.data, bytes) else event.data
        )

        # сериализация по ключу (важно для корректной FSM)
        async with self.fsm.lock(key, ttl_ms=20000):
            ctx = await self.fsm.get_ctx(key)

            # Ищем хендлер для этого callback
            handler = self.callback_handlers.get(callback_data)
            if handler is None:
                # Если точного совпадения нет, пробуем найти по префиксу (например "limit:")
                for prefix, h in self.callback_handlers.items():
                    if callback_data.startswith(prefix):
                        handler = h
                        break

            if handler:
                await handler(event, ctx)
