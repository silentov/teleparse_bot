from langchain.chat_models import init_chat_model, BaseChatModel
from config import Settings


def get_model(config: Settings) -> BaseChatModel:
    return init_chat_model(
        model=config.llm.model,
        model_provider="deepseek",
        temperature=config.llm.temperature,
        timeout=config.llm.timeout,
        max_retries=config.llm.max_retries,
    )
