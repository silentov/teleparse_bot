"""Доменные и инфраструктурные исключения проекта."""

from __future__ import annotations


class AppError(Exception):
    """Базовая ошибка приложения."""


class ConfigurationError(AppError):
    """Ошибка конфигурации приложения."""


class InvalidUserInputError(AppError):
    """Ошибка пользовательского ввода."""


class TelegramAccessError(AppError):
    """Ошибка взаимодействия с Telegram API."""


class UserBotNotStartedError(AppError):
    """Ошибка использования UserBot до его запуска."""


class LLMProviderError(AppError):
    """Ошибка взаимодействия с LLM-провайдером."""


class LLMEmptyResponseError(LLMProviderError):
    """LLM вернул пустой ответ."""


class FSMStorageError(AppError):
    """Ошибка хранения/чтения контекста FSM."""
