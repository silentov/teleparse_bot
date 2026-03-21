from __future__ import annotations

import time
from typing import Any

from redis.asyncio import Redis
import orjson

from .keys import RedisKeys
from app_logger import get_logger


LOGGER = get_logger(component="redis_service")


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

    async def expire(self, key: str, ttl_sec: int) -> bool:
        return bool(await self._redis.expire(key, ttl_sec))

    async def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        payload = await self._redis.get(key)
        if payload is None:
            return None
        return orjson.loads(payload)

    async def set_json(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_sec: int | None = None,
        only_if_not_exists: bool = False,
    ) -> bool:
        payload = orjson.dumps(value)
        result = await self._redis.set(
            key,
            payload,
            ex=ttl_sec,
            nx=only_if_not_exists,
        )
        return bool(result)

    async def get_fsm_context(
        self,
        chat_id: int,
        user_id: int,
        *,
        touch_ttl_sec: int | None = None,
    ) -> dict[str, Any] | None:
        key = RedisKeys.fsm_context(chat_id, user_id)
        raw = await self._redis.hgetall(key)  # pyright: ignore[reportGeneralTypeIssues]
        if not raw:
            return None

        try:
            data = orjson.loads(raw.get("data", "{}"))
        except orjson.JSONDecodeError as e:
            LOGGER.error("Ошибка декодинга данных: {}", e)
            data = {}

        if touch_ttl_sec is not None:
            await self._redis.expire(key, touch_ttl_sec)

        return {
            "key": (chat_id, user_id),
            "state": raw.get("state", "default"),
            "data": data,
            "updated_at": raw.get("updated_at", ""),
        }

    async def set_fsm_state(
        self,
        chat_id: int,
        user_id: int,
        state: str,
        *,
        ttl_sec: int | None = None,
    ) -> bool:
        key = RedisKeys.fsm_context(chat_id, user_id)
        LOGGER.info(
            "Persist FSM state: state={} chat_id={} user_id={}",
            state,
            chat_id,
            user_id,
        )

        result = await self._redis.hset(
            key, mapping={"state": state, "updated_at": str(int(time.time()))}
        )  # pyright: ignore[reportGeneralTypeIssues]

        if ttl_sec is not None:
            await self._redis.expire(key, ttl_sec)
        return bool(result)

    async def set_fsm_data(
        self,
        chat_id: int,
        user_id: int,
        data: dict[str, Any],
        *,
        ttl_sec: int | None = None,
    ) -> bool:
        key = RedisKeys.fsm_context(chat_id, user_id)
        LOGGER.info(
            "Persist FSM data: keys={} chat_id={} user_id={}",
            sorted(data.keys()),
            chat_id,
            user_id,
        )

        result = await self._redis.hset(
            key,
            mapping={
                "data": orjson.dumps(data),
                "updated_at": str(int(time.time())),
            },
        )  # pyright: ignore[reportGeneralTypeIssues]

        if ttl_sec is not None:
            await self._redis.expire(key, ttl_sec)

        return bool(result)

    async def update_fsm_data(
        self,
        chat_id: int,
        user_id: int,
        *,
        ttl_sec: int | None = None,
        **data: Any,
    ) -> bool:
        key = RedisKeys.fsm_context(chat_id, user_id)

        LOGGER.info("Обновляем данные в Redis, chat_id: {}", chat_id)

        # Get existing data to merge
        raw = await self._redis.hgetall(key)  # pyright: ignore[reportGeneralTypeIssues]
        existing_data = {}
        if raw and "data" in raw:
            try:
                existing_data = orjson.loads(raw["data"])
            except orjson.JSONDecodeError:
                existing_data = {}

        # Merge with new data
        merged_data = {**existing_data, **data}

        # Save back to Redis
        result = await self._redis.hset(
            key,
            mapping={
                "data": orjson.dumps(merged_data),
                "updated_at": str(int(time.time())),
            },
        )  # pyright: ignore[reportGeneralTypeIssues]

        if ttl_sec is not None:
            await self._redis.expire(key, ttl_sec)

        return bool(result)

    async def reset_fsm(self, chat_id: int, user_id: int) -> int:
        key = RedisKeys.fsm_context(chat_id, user_id)
        LOGGER.info("Сбрасываем контекст для {}", user_id)
        return await self._redis.delete(key)
