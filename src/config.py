from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import SecretStr, field_validator, model_validator, BaseModel, Field
from pydantic.networks import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger

from exceptions import ConfigurationError


class Environment(str, Enum):
    LOCAL = "local"
    PROD = "prod"


class AppSecrets(BaseModel):
    name: str = "Граппер"
    api_id: SecretStr = Field(default=SecretStr(""))
    api_hash: SecretStr = Field(default=SecretStr(""))
    token: SecretStr = Field(default=SecretStr(""))

    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        extra="ignore",
    )

    @field_validator("api_id", "api_hash", "token")
    @classmethod
    def validate_non_empty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Secret value must not be empty")
        return value


class RedisSecrets(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    username: str | None = None
    password: SecretStr | None = None

    max_connections: int = 20
    socket_connect_timeout: float = 5.0
    socket_timeout: float = 5.0
    health_check_interval: int = 30
    decode_responses: bool = True
    ttl_second: int = 1800

    # Можно либо задать REDIS_URL целиком, либо собрать его из частей.
    url: RedisDsn | None = None

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        extra="ignore",
    )

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("REDIS_HOST must not be empty")
        return value

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("REDIS_PORT must be in range 1..65535")
        return value

    @field_validator("db")
    @classmethod
    def validate_db(cls, value: int) -> int:
        if value < 0:
            raise ValueError("REDIS_DB must be >= 0")
        return value

    @model_validator(mode="after")
    def build_url_if_needed(self) -> "RedisSecrets":
        if self.url is None:
            auth = ""
            if self.username and self.password:
                auth = f"{self.username}:{self.password.get_secret_value()}@"
            elif self.password:
                auth = f":{self.password.get_secret_value()}@"

            self.url = RedisDsn(f"redis://{auth}{self.host}:{self.port}/{self.db}")
        return self


class LLMSecrets(BaseModel):
    model: str = ""
    temperature: float = 1.0
    timeout: int = 30
    tokens: int = 8000
    max_retries: int = 0
    api_key: SecretStr = Field(default=SecretStr(""))
    api_url: str | None = None

    system_prompt: str = ""

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        extra="ignore",
    )

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Температура модели должна быть >= 0.0")
        return value


class Settings(BaseSettings):
    """
    Корневая конфигурация приложения.

    Источники:
    1. init kwargs
    2. env vars
    3. .env
    4. Docker Secrets (/run/secrets или указанная директория)
    5. default values
    """

    env: Environment = Environment.LOCAL

    app: AppSecrets = AppSecrets()
    redis: RedisSecrets = RedisSecrets()
    llm: LLMSecrets = LLMSecrets()

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def from_sources(
        cls,
        *,
        app_env: Environment,
        env_file: str | Path | None = None,
        secrets_dir: str | Path | None = None,
    ) -> "Settings":
        kwargs: dict[str, Any] = {"env": app_env}

        if env_file is not None:
            kwargs["_env_file"] = str(env_file)

        if secrets_dir is not None:
            kwargs["_secrets_dir"] = str(secrets_dir)

        return cls(**kwargs)

    def safe_dump(self) -> dict:
        return {
            "bot": {
                "name": self.app.name,
                "api_id": self._mask_secret(self.app.api_id),
                "api_hash": self._mask_secret(self.app.api_hash),
                "token": self._mask_secret(self.app.token),
            },
            "redis": {
                "host": self.redis.host,
                "port": self.redis.port,
                "db": self.redis.db,
                "username": self.redis.username,
                "password": "***" if self.redis.password else None,
                # "url": self._mask_dsn(str(self.redis.url)) if self.redis.url else None,
            },
            "llm": {
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "timeout": self.llm.timeout,
                "tokens": self.llm.tokens,
                "api_key": self._mask_secret(self.llm.api_key),
            },
        }

    @staticmethod
    def _mask_dsn(value: str) -> str:
        import re

        return re.sub(r":([^:@/]+)@", ":***@", value)

    def _mask_secret(self, value: str | SecretStr | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
        else:
            raw = value

        raw = raw.strip()
        if not raw:
            return "***"

        if len(raw) <= 8:
            masked = "*" * len(raw)
        else:
            masked = f"{raw[:4]}{'*' * (len(raw) - 8)}{raw[-4:]}"

        fingerprint = sha256(raw.encode("utf-8")).hexdigest()[:8]
        return f"{masked} len={len(raw)} sha256={fingerprint}"


def resolve_local_env_file() -> Path:
    """
    Ожидаем файл: <project_root>/src/.secrets/.env
    """
    base_dir = Path(__file__).resolve()
    # logger.debug("{}", base_dir)
    project_root = base_dir.parents[1]
    # logger.debug("{}", project_root)

    env_file = project_root / "src" / ".secrets" / ".env"
    return env_file


def resolve_prod_secrets_dir() -> Path | None:
    candidates = [
        Path("/run/secrets"),
        Path("/var/run/secrets"),
    ]

    env_secrets_dir = os.getenv("SECRETS_DIR")
    if env_secrets_dir:
        candidates.insert(0, Path(env_secrets_dir).expanduser())

    for candidate in candidates:
        try:
            path = candidate.resolve()
        except OSError:
            continue

        if not path.exists() or not path.is_dir():
            continue

        try:
            if any(item.is_file() for item in path.iterdir()):
                return path
        except OSError:
            continue


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw_env = os.getenv("APP_ENV", "local").strip().lower()
    try:
        app_env = Environment(raw_env)
    except ValueError as exc:
        raise ConfigurationError(f"Неподдерживаемый APP_ENV: {raw_env}") from exc

    if app_env is Environment.LOCAL:
        env_file = resolve_local_env_file()

        if not env_file.exists() or not env_file.is_file():
            raise ConfigurationError(f"Local env file not found: {env_file}")

        logger.info("Режим local, загружаю env_file: {}", env_file)

        settings = Settings.from_sources(
            app_env=app_env,
            env_file=env_file,
            secrets_dir=None,
        )
    else:
        secrets_dir = resolve_prod_secrets_dir()

        if secrets_dir is None:
            raise ConfigurationError(
                "APP_ENV=prod, но директория Docker Secrets не найдена"
            )

        logger.info("Режим prod, загружаю secrets_dir: {}", secrets_dir)

        settings = Settings.from_sources(
            app_env=app_env,
            env_file=None,
            secrets_dir=secrets_dir,
        )

    logger.info("Загружены секреты:\n{}", settings.safe_dump())
    return settings
