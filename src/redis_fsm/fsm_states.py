from enum import Enum


class FSMState(str, Enum):
    """Состояния FSM для бота."""

    DEFAULT = "default"
    WAIT_PARSE_START = "wait_parse_start"
    WAIT_CHANNEL = "wait_channel"
    WAIT_LIMIT = "wait_limit"
    WAIT_CUSTOM_LIMIT = "wait_custom_limit"  # Для ручного ввода лимита
