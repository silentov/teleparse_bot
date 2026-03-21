from pydantic import BaseModel, Field


class TelegramMessageDTO(BaseModel):
    """Минимальная DTO-модель сообщения Telegram для межслойного контракта."""

    id: int = Field(..., description="ID сообщения")
    text: str = Field(default="", description="Текст сообщения")


class ChannelMessagesResult(BaseModel):
    """Результат получения сообщений из канала."""

    channel_name: str = Field(..., description="Имя/заголовок канала")
    channel_input: str = Field(..., description="Исходное имя канала из запроса")
    messages: list[TelegramMessageDTO] = Field(
        default_factory=list,
        description="Список полученных сообщений",
    )


class StructuredMessage(BaseModel):
    model_message: str = Field(..., description="Ответ модели")
    urls: list[str] = Field(..., description="Список ссылок на сообщения")


class LLMSummaryResult(BaseModel):
    """Нормализованный ответ LLM для использования в приложении."""

    model_message: str = Field(..., description="Сгенерированное summary")
    urls: list[str] = Field(default_factory=list, description="Ссылки из ответа LLM")
