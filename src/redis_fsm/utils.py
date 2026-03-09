from redis.asyncio import Redis, ConnectionPool

# Синглтон для Redis connection pool
_redis_pool: ConnectionPool | None = None
_redis_instance: Redis | None = None


# def get_redis() -> Redis:
#     """Возвращает синглтон Redis-клиент с общим пулом соединений."""
#     global _redis_pool, _redis_instance

#     if _redis_instance is None:
#         if not config.redis_url:
#             raise ValueError("REDIS_URL не настроен")

#         _redis_pool = ConnectionPool.from_url(
#             config.redis_url,
#             username=config.redis_username,
#             password=config.redis_password,
#             decode_responses=True,
#             max_connections=config.redis_max_connections or 10,
#         )
#         _redis_instance = Redis.from_pool(connection_pool=_redis_pool)

#     return _redis_instance
