from pydantic import BaseModel, Field


class StructuredMessage(BaseModel):
    model_message: str = Field(..., description="Ответ модели")
    urls: list[str] = Field(..., description="Список ссылок на сообщения")
