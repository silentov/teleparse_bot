from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Tuple
from dataclasses import dataclass, field

from app_logger import get_logger

from infrastructure.redis import RedisService, LockService, RedisLock
from fsm.fsm_states import FSMState

Key = Tuple[int, int]
LOGGER = get_logger(component="fsm")


@dataclass
class FSMContext:
    key: Key
    state: str = FSMState.DEFAULT
    data: Dict[str, Any] = field(default_factory=dict)


class FSM:
    def __init__(
        self,
        redis_service: RedisService,
        lock_service: LockService,
        *,
        ttl_seconds: int = 1800,
    ):
        self.redis_service = redis_service
        self.lock_service = lock_service
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _normalize_state(state: str | Enum) -> str:
        if isinstance(state, Enum):
            return str(state.value)
        return str(state)

    async def get_ctx(self, key: Key) -> FSMContext:
        chat_id, user_id = key
        fsm_data = await self.redis_service.get_fsm_context(
            chat_id,
            user_id,
            touch_ttl_sec=self.ttl_seconds,
        )
        if fsm_data is None:
            # новая сессия
            ctx = FSMContext(key=key, state=FSMState.DEFAULT, data={})
            await self._save_ctx(ctx)
            return ctx

        return FSMContext(key=key, state=fsm_data["state"], data=fsm_data["data"])

    async def _save_ctx(self, ctx: FSMContext) -> None:
        chat_id, user_id = ctx.key
        normalized_state = self._normalize_state(ctx.state)
        ctx.state = normalized_state

        await self.redis_service.set_fsm_state(
            chat_id,
            user_id,
            normalized_state,
            ttl_sec=self.ttl_seconds,
        )
        await self.redis_service.set_fsm_data(
            chat_id,
            user_id,
            ctx.data,
            ttl_sec=self.ttl_seconds,
        )

    async def set_state(self, ctx: FSMContext, state: str | Enum) -> None:
        current_state = self._normalize_state(ctx.state)
        next_state = self._normalize_state(state)

        if current_state == next_state:
            return

        chat_id, user_id = ctx.key
        LOGGER.info(
            "FSM transition: {} -> {} (chat_id={}, user_id={})",
            current_state,
            next_state,
            chat_id,
            user_id,
        )

        ctx.state = next_state
        await self.redis_service.set_fsm_state(
            chat_id,
            user_id,
            next_state,
            ttl_sec=self.ttl_seconds,
        )

    async def update_data(self, ctx: FSMContext, **patch: Any) -> None:
        if not patch:
            return

        ctx.data.update(patch)
        chat_id, user_id = ctx.key
        await self.redis_service.set_fsm_data(
            chat_id,
            user_id,
            ctx.data,
            ttl_sec=self.ttl_seconds,
        )

    async def reset(self, key: Key) -> None:
        chat_id, user_id = key
        default_state = self._normalize_state(FSMState.DEFAULT)
        await self.redis_service.set_fsm_state(
            chat_id,
            user_id,
            default_state,
            ttl_sec=self.ttl_seconds,
        )
        await self.redis_service.set_fsm_data(
            chat_id,
            user_id,
            {},
            ttl_sec=self.ttl_seconds,
        )

    def lock(self, key: Key, *, ttl_ms: int = 15000) -> RedisLock:
        chat_id, user_id = key
        return self.lock_service.fsm(chat_id, user_id, ttl_ms=ttl_ms)

    def processing_key(self, key: Key) -> str:
        chat_id, user_id = key
        return f"fsm:processing:{chat_id}:{user_id}"
