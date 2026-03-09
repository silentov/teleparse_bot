from __future__ import annotations

import asyncio
import uuid
from typing import Self

from redis.asyncio import Redis
from loguru import logger

_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
"""

_EXTEND_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("PEXPIRE", KEYS[1], ARGV[2])
else
  return 0
end
"""


class RedisLock:
    def __init__(self, redis: Redis, key: str, ttl_ms: int = 15_000) -> None:
        self._redis = redis
        self._key = key
        self._ttl_ms = ttl_ms
        self._token = str(uuid.uuid4())
        self._is_acquired = False

    @property
    def key(self) -> str:
        return self._key

    @property
    def token(self) -> str:
        return self._token

    @property
    def ttl_ms(self) -> int:
        return self._ttl_ms

    @property
    def is_acquired(self) -> bool:
        return self._is_acquired

    async def acquire(self, *, wait_ms: int = 5_000, retry_ms: int = 50) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_ms / 1000
        logger.info("key: {}, ttl: {}", self._key, self._ttl_ms)
        while loop.time() < deadline:
            ok = await self._redis.set(
                self._key,
                self._token,
                nx=True,
                px=self._ttl_ms,
            )
            if ok:
                self._is_acquired = True
                return True

            await asyncio.sleep(retry_ms / 1000)

        return False

    async def extend(self, ttl_ms: int | None = None) -> bool:
        if not self._is_acquired:
            return False

        new_ttl = ttl_ms or self._ttl_ms
        result = await self._redis.eval(
            _EXTEND_LOCK_LUA,
            1,
            self._key,
            self._token,
            new_ttl,
        )  # pyright: ignore[reportGeneralTypeIssues]
        return bool(result)

    async def release(self) -> bool:
        if not self._is_acquired:
            return False

        result = await self._redis.eval(
            _RELEASE_LOCK_LUA,
            1,
            self._key,
            self._token,
        )  # pyright: ignore[reportGeneralTypeIssues]
        self._is_acquired = False
        return bool(result)

    async def __aenter__(self) -> Self:
        ok = await self.acquire()
        if not ok:
            raise TimeoutError(f"Lock timeout: {self._key}")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()
