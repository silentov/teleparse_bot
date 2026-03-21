from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import ValidationError

from app_logger import get_logger
from config import Settings
from exceptions import LLMEmptyResponseError, LLMProviderError

from .schema import LLMSummaryResult, StructuredMessage, TelegramMessageDTO


LOGGER = get_logger(component="llm_provider")


class LLMProvider:
    def __init__(self, config: Settings) -> None:
        self._model = init_chat_model(
            model=config.llm.model,
            model_provider="deepseek",
            api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            timeout=config.llm.timeout,
            max_retries=config.llm.max_retries,
            disabled_params={"tool_choice": None}
            #base_url="aaaaaa",
        )

        self._system_prompt = SystemMessage(config.llm.system_prompt)
    
    async def send_message(
        self,
        messages: list[TelegramMessageDTO],
    ) -> LLMSummaryResult:
        structured_model = self._model.with_structured_output(StructuredMessage)

        input_message = self._prepare_message(messages)
        LOGGER.info("Отправляем {} сообщений в LLM", len(messages))

        try:
            response = await structured_model.ainvoke(
                input=[self._system_prompt, input_message],
                config={"max_concurrency": 5},
            )
        except Exception as exc:
            raise LLMProviderError("Ошибка при вызове LLM") from exc

        LOGGER.info("LLM ответ получен успешно")

        if response is None:
            raise LLMEmptyResponseError("LLM вернул пустой ответ")

        if isinstance(response, StructuredMessage):
            structured_response = response
        elif isinstance(response, dict):
            try:
                structured_response = StructuredMessage.model_validate(response)
            except ValidationError as exc:
                raise LLMProviderError("Ответ LLM не прошел валидацию") from exc
        else:
            model_dump = getattr(response, "model_dump", None)
            if not callable(model_dump):
                raise LLMProviderError(
                    f"Неожиданный тип ответа LLM: {response.__class__.__name__}"
                )

            try:
                structured_response = StructuredMessage.model_validate(model_dump())
            except ValidationError as exc:
                raise LLMProviderError("Ответ LLM не прошел валидацию") from exc

        return LLMSummaryResult(
            model_message=structured_response.model_message,
            urls=structured_response.urls,
        )

    @staticmethod
    def _prepare_message(messages: list[TelegramMessageDTO]) -> HumanMessage:
        content = []

        for msg in messages:
            text = msg.text
            content.append(
                {
                    "type": "text",
                    "text": f"[id={msg.id}] {text}",
                }
            )
        return HumanMessage(content=content)
