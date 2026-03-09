from __future__ import annotations

import json
import time
from typing import Any

from redis.asyncio import Redis

from .keys import RedisKeys


class RedisService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @property
    def client(self) -> Redis:
        return self._redis

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ttl_sec: int | None = None,
        only_if_not_exists: bool = False,
    ) -> bool:
        result = await self._redis.set(
            key,
            value,
            ex=ttl_sec,
            nx=only_if_not_exists,
        )
        return bool(result)

    async def delete(self, key: str) -> int:
        return await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def expire(self, key: str, ttl_sec: int) -> bool:
        return bool(await self._redis.expire(key, ttl_sec))

    async def incr(self, key: str, amount: int = 1) -> int:
        return await self._redis.incr(key, amount)

    async def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        payload = await self._redis.get(key)
        if payload is None:
            return None
        return json.loads(payload)

    async def set_json(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_sec: int | None = None,
        only_if_not_exists: bool = False,
    ) -> bool:
        payload = json.dumps(value, ensure_ascii=False)
        result = await self._redis.set(
            key,
            payload,
            ex=ttl_sec,
            nx=only_if_not_exists,
        )
        return bool(result)

    async def get_user_profile(self, user_id: int) -> dict[str, Any] | None:
        data = await self.get_json(RedisKeys.user_profile(user_id))
        if data is None:
            return None
        if not isinstance(data, dict):
            raise TypeError(
                f"Expected dict for user profile, got {type(data).__name__}"
            )
        return data

    async def set_user_profile(
        self,
        user_id: int,
        value: dict[str, Any],
        *,
        ttl_sec: int | None = None,
    ) -> bool:
        return await self.set_json(
            RedisKeys.user_profile(user_id),
            value,
            ttl_sec=ttl_sec,
        )

    async def get_user_state(self, user_id: int) -> str | None:
        return await self.get(RedisKeys.user_state(user_id))

    async def set_user_state(
        self,
        user_id: int,
        state: str,
        *,
        ttl_sec: int | None = None,
    ) -> bool:
        return await self.set(
            RedisKeys.user_state(user_id),
            state,
            ttl_sec=ttl_sec,
        )

    async def get_fsm_context(
        self, chat_id: int, user_id: int
    ) -> dict[str, Any] | None:
        key = RedisKeys.fsm_context(chat_id, user_id)
        raw = await self._redis.hgetall(key)  # pyright: ignore[reportGeneralTypeIssues]
        if not raw:
            return None

        try:
            data = json.loads(raw.get("data", "{}"))
        except json.JSONDecodeError:
            data = {}

        # Update TTL
        await self._redis.expire(key, 1800)

        return {
            "key": (chat_id, user_id),
            "state": raw.get("state", "default"),
            "data": data,
            "updated_at": raw.get("updated_at", ""),
        }

    async def set_fsm_state(self, chat_id: int, user_id: int, state: str) -> bool:
        key = RedisKeys.fsm_context(chat_id, user_id)
        result = await self._redis.hset(
            key, mapping={"state": state, "updated_at": str(int(time.time()))}
        )  # pyright: ignore[reportGeneralTypeIssues]
        # Keep the same TTL as for user state
        await self._redis.expire(key, 1800)
        return bool(result)

    async def update_fsm_data(self, chat_id: int, user_id: int, **data) -> bool:
        key = RedisKeys.fsm_context(chat_id, user_id)

        # Get existing data to merge
        raw = await self._redis.hgetall(key)  # pyright: ignore[reportGeneralTypeIssues]
        existing_data = {}
        if raw and "data" in raw:
            try:
                existing_data = json.loads(raw["data"])
            except json.JSONDecodeError:
                existing_data = {}

        # Merge with new data
        merged_data = {**existing_data, **data}

        # Save back to Redis
        result = await self._redis.hset(
            key,
            mapping={
                "data": json.dumps(merged_data, ensure_ascii=False),
                "updated_at": str(int(time.time())),
            },
        )  # pyright: ignore[reportGeneralTypeIssues]
        # Keep the same TTL as for user state
        await self._redis.expire(key, 1800)
        return bool(result)

    async def reset_fsm(self, chat_id: int, user_id: int) -> int:
        key = RedisKeys.fsm_context(chat_id, user_id)
        return await self._redis.delete(key)
