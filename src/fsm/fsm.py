from __future__ import annotations

from typing import Any, Dict, Tuple
from dataclasses import dataclass, field


from infrastructure.redis import RedisService, LockService, RedisKeys, RedisLock
from fsm.fsm_states import FSMState

Key = Tuple[int, int]


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

    async def get_ctx(self, key: Key) -> FSMContext:
        chat_id, user_id = key
        fsm_data = await self.redis_service.get_fsm_context(chat_id, user_id)
        if fsm_data is None:
            # новая сессия
            ctx = FSMContext(key=key, state=FSMState.DEFAULT, data={})
            await self._save_ctx(ctx)
            return ctx

        return FSMContext(key=key, state=fsm_data["state"], data=fsm_data["data"])

    async def _save_ctx(self, ctx: FSMContext) -> None:
        chat_id, user_id = ctx.key
        # Сохраняем состояние и данные отдельно
        await self.redis_service.set_fsm_state(chat_id, user_id, ctx.state)
        if ctx.data:
            await self.redis_service.update_fsm_data(chat_id, user_id, **ctx.data)
        await self.redis_service.expire(
            RedisKeys.fsm_context(chat_id, user_id), self.ttl_seconds
        )

    async def set_state(self, ctx: FSMContext, state: str) -> None:
        ctx.state = state
        await self._save_ctx(ctx)

    async def update_data(self, ctx: FSMContext, **patch: Any) -> None:
        ctx.data.update(patch)
        await self._save_ctx(ctx)

    async def reset(self, key: Key) -> None:
        chat_id, user_id = key
        await self.redis_service.reset_fsm(chat_id, user_id)

    def lock(self, key: Key, *, ttl_ms: int = 15000) -> RedisLock:
        chat_id, user_id = key
        return self.lock_service.fsm(chat_id, user_id, ttl_ms=ttl_ms)
