from loguru import logger

import asyncio
from telethon import TelegramClient
from bot_client import MainBot
from config import get_settings
from infrastructure.redis import RedisManager, RedisService, LockService
from redis_fsm import RedisFSM, RedisFSMDispatcher
from userbot_client import UserBot


async def main():
    settings = get_settings()

    redis_manager = RedisManager(config=settings)

    logger.info("Запускаем Redis...")
    await redis_manager.start()

    try:
        r_client = redis_manager.get_client()

        redis_service = RedisService(redis=r_client)
        lock_service = LockService(redis=r_client)

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

        fsm = RedisFSM(redis_service, lock_service, ttl_seconds=30 * 60)
        dispatcher = RedisFSMDispatcher(fsm=fsm)

        bot = MainBot(
            config=settings,
            client=tbot_client,
            userbot=UserBot(client=tuserbot_client),
            fsm=fsm,
            dispatcher=dispatcher,
        )

        logger.info("Запускаем бота...")
        await bot.run()
    except Exception as e:
        logger.exception("Ошибка: ")
    finally:
        await redis_manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
