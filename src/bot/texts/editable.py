from typing import LiteralString

from llm.schema import ChannelMessagesResult, LLMSummaryResult


def get_limit_text(ch: LiteralString) -> str:
    return f"📊 Канал: **{ch}**\n\nСколько постов получить?"


def get_summary_text(
    ch: str,
    id_list: list[int],
    channel_result: ChannelMessagesResult,
    summary: LLMSummaryResult,
) -> str:
    links = "\n".join([f"{ch}/{msg_id}" for msg_id in id_list])
    return (
        "✅ Получено\n"
        f" **{links}**\n"
        f"сообщений из канала **{channel_result.channel_name}**\n"
        f"Саммари:\n{summary.model_message}"
    )


def load_posts_text(limit: int, channel: str) -> str:
    return f"⏳ Получаю {limit} постов из канала **{channel}**..."


def error_text(e: Exception) -> str:
    return f"❌ Ошибка: {e}"

