from __future__ import annotations

from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError

from config import Settings
from app_logger import get_logger


LOGGER = get_logger(component="redis_manager")


class RedisManager:
    def __init__(
        self,
        config: Settings,
    ) -> None:
        self._redis_url = config.redis.url
        self._max_connections = config.redis.max_connections
        self._socket_connect_timeout = config.redis.socket_connect_timeout
        self._socket_timeout = config.redis.socket_timeout
        self._health_check_interval = config.redis.health_check_interval
        self._decode_responses = config.redis.decode_responses
        self._fsm_ttl_seconds = config.redis.ttl_second

        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        self._pool = ConnectionPool.from_url(
            str(self._redis_url),
            max_connections=self._max_connections,
            decode_responses=self._decode_responses,
            socket_connect_timeout=self._socket_connect_timeout,
            socket_timeout=self._socket_timeout,
            health_check_interval=self._health_check_interval,
        )

        self._client = Redis.from_pool(self._pool)

        try:
            LOGGER.info("Redis ping")
            await self._client.ping()  # pyright: ignore[reportGeneralTypeIssues]
        except RedisError as e:
            LOGGER.error("Ошибка в тестовом подключении к Redis: {}", e)
            await self.stop()
            raise
        else:
            LOGGER.info("OK")

        self._started = True

    # TODO: сделать ретраи
    def get_client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("RedisManager is not started")
        return self._client

    @property
    def fsm_ttl_seconds(self) -> int:
        return self._fsm_ttl_seconds

    async def stop(self) -> None:
        if self._client is not None:
            LOGGER.info("Разрываем подключение к Redis")
            await self._client.aclose()
            self._client = None

        self._pool = None
        self._started = False

    async def ping(self) -> bool:
        client = self.get_client()
        result = await client.ping()  # pyright: ignore[reportGeneralTypeIssues]
        return bool(result)
