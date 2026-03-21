import asyncio
import os
from pathlib import Path

from telethon import TelegramClient

from bot.bot_client import MainBot
from config import get_settings
from infrastructure.redis import RedisManager, RedisService, LockService
from fsm import FSM, RedisFSMDispatcher
from bot.userbot_client import UserBot
from app_logger import setup_logger, get_logger
from exceptions import AppError
from llm import LLMProvider


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    app_env = os.getenv("APP_ENV", "local").strip().lower()

    setup_logger(
        app_name="teleparse_bot",
        env=app_env,
        level="INFO",
        log_dir=LOG_DIR,
        log_json=False,
        log_to_file=True,
        intercept_std_logging=True,
    )

    LOGGER = get_logger(component="bootstrap")
    LOGGER.info("Custom logger")

    settings = get_settings()

    redis_manager = RedisManager(config=settings)

    LOGGER.info("Запускаем Redis...")
    await redis_manager.start()

    try:
        r_client = redis_manager.get_client()

        redis_service = RedisService(redis=r_client)
        lock_service = LockService(redis=r_client)

        llm_provider = LLMProvider(config=settings)

        tbot_client = TelegramClient(
            "bot_session",
            int(settings.app.api_id.get_secret_value()),
            str(settings.app.api_hash.get_secret_value()),
        )

        tuserbot_client = TelegramClient(
            "async_session",
            int(settings.app.api_id.get_secret_value()),
            str(settings.app.api_hash.get_secret_value()),
        )

        fsm = FSM(
            redis_service,
            lock_service,
            ttl_seconds=settings.redis.ttl_second,
        )
        dispatcher = RedisFSMDispatcher(fsm=fsm)

        bot = MainBot(
            config=settings,
            client=tbot_client,
            userbot=UserBot(client=tuserbot_client),
            fsm=fsm,
            dispatcher=dispatcher,
            llm_provider=llm_provider,
        )

        LOGGER.info("Запускаем бота...")
        await bot.run()
    except AppError as e:
        LOGGER.exception("Ошибка приложения: {}", e)
    except Exception as e:
        LOGGER.exception("Ошибка: {}", e)
    finally:
        LOGGER.complete()
        await redis_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
