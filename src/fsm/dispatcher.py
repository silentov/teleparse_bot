from __future__ import annotations

from telethon import events
from typing import Awaitable, Callable

from fsm import FSM, FSMContext

StateHandler = Callable[[events.NewMessage.Event, FSMContext], Awaitable[None]]
CallbackHandler = Callable[[events.CallbackQuery.Event, FSMContext], Awaitable[None]]


class RedisFSMDispatcher:
    def __init__(self, fsm: FSM):
        self.fsm = fsm
        self.handlers: dict[str, Callable[..., Awaitable[None]]] = {}
        self.callback_handlers: dict[str, Callable[..., Awaitable[None]]] = {}

    @staticmethod
    def run_outside_lock(handler: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        """Маркер для хендлеров с долгими внешними операциями.

        Такие хендлеры выполняются вне долгоживущего FSM lock.
        """
        setattr(handler, "_run_outside_fsm_lock", True)
        return handler

    @staticmethod
    def _should_run_outside_lock(handler: Callable[..., Awaitable[None]]) -> bool:
        return bool(getattr(handler, "_run_outside_fsm_lock", False))

    async def _try_mark_processing(self, key: tuple[int, int], *, ttl_ms: int = 120000) -> bool:
        """Пытается выставить флаг активной обработки пользователя.

        Флаг выставляется под коротким FSM lock, чтобы избежать гонки между апдейтами.
        """
        chat_id, user_id = key
        processing_key = self.fsm.processing_key(key)
        async with self.fsm.lock(key, ttl_ms=5000):
            is_processing = await self.fsm.redis_service.get(processing_key)
            if is_processing is not None:
                return False

            await self.fsm.redis_service.set(
                processing_key,
                "1",
                ttl_sec=max(1, ttl_ms // 1000),
                only_if_not_exists=True,
            )

            # refresh TTL контекста, чтобы не протух во время долгой операции
            await self.fsm.redis_service.get_fsm_context(
                chat_id,
                user_id,
                touch_ttl_sec=self.fsm.ttl_seconds,
            )
            return True

    async def _clear_processing(self, key: tuple[int, int]) -> None:
        await self.fsm.redis_service.client.delete(self.fsm.processing_key(key))

    async def dispatch(self, event: events.NewMessage.Event) -> None:
        chat_id = event.chat_id
        user_id = event.sender_id
        if chat_id is None or user_id is None:
            return

        key = (chat_id, user_id)

        # Короткая критическая секция: только чтение контекста и выбор маршрута
        async with self.fsm.lock(key, ttl_ms=5000):
            ctx = await self.fsm.get_ctx(key)

            text = (event.raw_text or "").strip()
            command_mode = text.startswith("/")

            if command_mode:
                handler = self.handlers.get(text)
                if handler is None:
                    handler = self.handlers.get("unknown_command")
            else:
                handler = self.handlers.get(ctx.state) or self.handlers.get("default")

        if handler is None:
            return

        if self._should_run_outside_lock(handler):
            marked = await self._try_mark_processing(key)
            if not marked:
                contention_handler = self.handlers.get("contention")
                if contention_handler:
                    async with self.fsm.lock(key, ttl_ms=5000):
                        fresh_ctx = await self.fsm.get_ctx(key)
                    await contention_handler(event, fresh_ctx)
                return

            try:
                async with self.fsm.lock(key, ttl_ms=5000):
                    fresh_ctx = await self.fsm.get_ctx(key)
                await handler(event, fresh_ctx)
            finally:
                await self._clear_processing(key)
            return

        async with self.fsm.lock(key, ttl_ms=5000):
            fresh_ctx = await self.fsm.get_ctx(key)
            await handler(event, fresh_ctx)

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

        # Короткая критическая секция: только чтение контекста и выбор маршрута
        async with self.fsm.lock(key, ttl_ms=5000):
            ctx = await self.fsm.get_ctx(key)

            # Ищем хендлер для этого callback
            handler = self.callback_handlers.get(callback_data)
            if handler is None:
                # Если точного совпадения нет, пробуем найти по префиксу (например "limit:")
                for prefix, h in self.callback_handlers.items():
                    if callback_data.startswith(prefix):
                        handler = h
                        break

        if handler is None:
            return

        if self._should_run_outside_lock(handler):
            marked = await self._try_mark_processing(key)
            if not marked:
                contention_handler = self.callback_handlers.get("contention")
                if contention_handler:
                    async with self.fsm.lock(key, ttl_ms=5000):
                        fresh_ctx = await self.fsm.get_ctx(key)
                    await contention_handler(event, fresh_ctx)
                return

            try:
                async with self.fsm.lock(key, ttl_ms=5000):
                    fresh_ctx = await self.fsm.get_ctx(key)
                await handler(event, fresh_ctx)
            finally:
                await self._clear_processing(key)
            return

        async with self.fsm.lock(key, ttl_ms=5000):
            fresh_ctx = await self.fsm.get_ctx(key)
            await handler(event, fresh_ctx)
