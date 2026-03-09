from __future__ import annotations

from redis.asyncio import Redis

from .keys import RedisKeys
from .lock import RedisLock


class LockService:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def by_key(self, key: str, *, ttl_ms: int = 15_000) -> RedisLock:
        return RedisLock(
            redis=self._redis,
            key=key,
            ttl_ms=ttl_ms,
        )

    def user_action(
        self, user_id: int, action: str, *, ttl_ms: int = 15_000
    ) -> RedisLock:
        return RedisLock(
            redis=self._redis,
            key=RedisKeys.lock_user_action(user_id, action),
            ttl_ms=ttl_ms,
        )

    def job(self, job_name: str, *, ttl_ms: int = 15_000) -> RedisLock:
        return RedisLock(
            redis=self._redis,
            key=RedisKeys.lock_job(job_name),
            ttl_ms=ttl_ms,
        )

    def resource(
        self,
        resource_type: str,
        resource_id: str | int,
        action: str,
        *,
        ttl_ms: int = 15_000,
    ) -> RedisLock:
        return RedisLock(
            redis=self._redis,
            key=RedisKeys.lock_resource(resource_type, resource_id, action),
            ttl_ms=ttl_ms,
        )

    def fsm(self, chat_id: int, user_id: int, *, ttl_ms: int = 15_000) -> RedisLock:
        return RedisLock(
            redis=self._redis, key=RedisKeys.fsm_lock(chat_id, user_id), ttl_ms=ttl_ms
        )
