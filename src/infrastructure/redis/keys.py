from __future__ import annotations


class RedisKeys:
    #PREFIX = "myapp"

    @classmethod
    def _join(cls, *parts: object) -> str:
        return ":".join(str(part) for part in parts)

    @classmethod
    def key(cls, *parts: object) -> str:
        return cls._join(*parts)

    @classmethod
    def lock(cls, *parts: object) -> str:
        return cls.key("lock", *parts)

    @classmethod
    def cache(cls, *parts: object) -> str:
        return cls.key("cache", *parts)

    @classmethod
    def session(cls, session_id: str) -> str:
        return cls.key("session", session_id)

    @classmethod
    def rate_limit(cls, scope: str, user_id: int) -> str:
        return cls.key("rate_limit", scope, user_id)

    @classmethod
    def lock_job(cls, job_name: str) -> str:
        return cls.lock("job", job_name)

    @classmethod
    def lock_resource(
        cls, resource_type: str, resource_id: str | int, action: str
    ) -> str:
        return cls.lock(resource_type, resource_id, action)

    @classmethod
    def fsm_context(cls, chat_id: int, user_id: int) -> str:
        return cls.key("fsm", chat_id, user_id)

    @classmethod
    def fsm_lock(cls, chat_id: int, user_id: int) -> str:
        return cls.lock("fsm", chat_id, user_id)
