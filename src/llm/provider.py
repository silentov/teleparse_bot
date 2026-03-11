from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from telethon.tl.types import Message

from .schema import StructuredMessage
from app_logger import get_logger
from config import Settings


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
        )

        self._system_prompt = SystemMessage(config.llm.system_prompt)

    async def send_message(self, tl_messages: list[Message]):
        structured_model = self._model.with_structured_output(StructuredMessage)
        
        input_message = self._prepare_message(tl_messages)

        LOGGER.info("{}", input_message)
        
        try:
            response = await structured_model.ainvoke(
                input=[self._system_prompt, input_message]
                #config={"max_concurrency": 5},
            )
            return response.model_dump()
        except Exception as e:
            LOGGER.exception("Ошибка {}, ({})", e, e.__class__.__name__)

    @staticmethod
    def _prepare_message(mes: list[Message]) -> HumanMessage:
        content = []

        for msg in mes:
            text = msg.message or ""
            content.append({
                "type": "text",
                "text": f"[id={msg.id}] {text}",
            })
        return HumanMessage(content=content)
