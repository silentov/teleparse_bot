from langchain.chat_models import init_chat_model, BaseChatModel


def get_model() -> BaseChatModel:
    return init_chat_model("deepseek:deepseek-chat", temperature=0)
