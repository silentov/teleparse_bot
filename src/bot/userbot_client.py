from telethon import TelegramClient
from telethon.errors import RPCError

from app_logger import get_logger
from exceptions import (
    InvalidUserInputError,
    TelegramAccessError,
    UserBotNotStartedError,
)
from llm.schema import ChannelMessagesResult, TelegramMessageDTO


LOGGER = get_logger(component="userbot")


class UserBot:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client
        self._started = False

    async def start(self) -> None:
        """Запускает UserBot клиент (вызывается один раз при старте приложения)."""
        if not self._started:
            await self._client.start()  # type: ignore
            self._started = True
            LOGGER.info("UserBot запущен")

    async def stop(self) -> None:
        """Останавливает UserBot клиент."""
        if self._started:
            await self._client.disconnect()  # pyright: ignore[reportGeneralTypeIssues]
            self._started = False
            LOGGER.info("UserBot остановлен")

    async def get_messages(
        self,
        chat_name: str | None,
        limit: int,
    ) -> ChannelMessagesResult:
        """Получает сообщения из канала."""
        if not self._started:
            raise UserBotNotStartedError(
                "UserBot не запущен. Вызовите start() перед использованием."
            )

        if not chat_name:
            raise InvalidUserInputError("Имя канала не может быть пустым")

        if limit <= 0:
            raise InvalidUserInputError("Лимит сообщений должен быть больше нуля")

        try:
            chat_info = await self._client.get_entity(chat_name)
            messages = await self._client.get_messages(entity=chat_info, limit=limit)
        except RPCError as exc:
            raise TelegramAccessError(
                f"Не удалось получить сообщения канала '{chat_name}'"
            ) from exc

        channel_name = getattr(chat_info, "title", None) or chat_name
        dto_messages = [
            TelegramMessageDTO(id=msg.id, text=(msg.message or "")) for msg in messages
        ]

        return ChannelMessagesResult(
            channel_name=channel_name,
            channel_input=chat_name,
            messages=dto_messages,
        )
