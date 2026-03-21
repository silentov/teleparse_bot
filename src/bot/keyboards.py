"""Клавиатуры (inline buttons) для бота."""

from telethon import Button


def main_menu():
    """Главное меню после /start."""
    return [
        [Button.inline("📥 Получить посты", data=b"cmd:get_messages")],
        [Button.inline("ℹ️ Помощь", data=b"cmd:help")],
    ]


def limit_picker():
    """Выбор количества постов."""
    return [
        [
            Button.inline("10", data=b"limit:10"),
            Button.inline("50", data=b"limit:50"),
            Button.inline("100", data=b"limit:100"),
        ],
        [Button.inline("📝 Своё значение", data=b"limit:custom")],
        [Button.inline("❌ Отмена", data=b"cmd:cancel")],
    ]


def cancel_button():
    """Кнопка отмены."""
    return [[Button.inline("❌ Отмена", data=b"cmd:cancel")]]


def back_to_menu():
    """Кнопка возврата в главное меню."""
    return [[Button.inline("🏠 В главное меню", data=b"cmd:main_menu")]]


def action_buttons():
    """Кнопки после успешного парсинга."""
    return [
        [Button.inline("📥 Ещё запрос", data=b"cmd:get_messages")],
        [Button.inline("🏠 В главное меню", data=b"cmd:main_menu")],
    ]
