from telethon import TelegramClient
from loguru import logger


class UserBot:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client
        self._started = False

    async def start(self) -> None:
        """Запускает UserBot клиент (вызывается один раз при старте приложения)."""
        if not self._started:
            await self._client.start()  # type: ignore
            self._started = True
            logger.info("UserBot started")

    async def stop(self) -> None:
        """Останавливает UserBot клиент."""
        if self._started:
            await self._client.disconnect()
            self._started = False
            logger.info("UserBot stopped")

    async def get_messages(self, chat_name: str | None, limit: int) -> dict:
        """Получает сообщения из канала."""
        if not self._started:
            raise RuntimeError(
                "UserBot не запущен. Вызовите start() перед использованием."
            )

        if not chat_name:
            raise ValueError("Имя канала не может быть пустым")

        chat_info = await self._client.get_entity(chat_name)
        messages = await self._client.get_messages(entity=chat_info, limit=limit)

        return {"messages": messages, "channel": chat_info}
