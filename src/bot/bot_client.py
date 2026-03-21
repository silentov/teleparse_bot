import asyncio
import signal

from telethon import TelegramClient, events

from app_logger import get_logger
from bot.keyboards import (
    action_buttons,
    back_to_menu,
    cancel_button,
    limit_picker,
    main_menu,
)
from bot.texts.const import (
    CANCEL_MESSAGE,
    CUSTOM_LIMIT_ERROR,
    CUSTOM_LIMIT_PROMPT,
    HELP_MESSAGE,
    LIMIT_ERROR_MESSAGE,
    MAIN_MENU_MESSAGE,
    START_MESSAGE,
    UNKNOWN_MESSAGE,
    WAITING_CHANNEL_MESSAGE,
)
from bot.texts.editable import (
    error_text,
    get_limit_text,
    get_summary_text,
    load_posts_text,
)
from bot.userbot_client import UserBot
from config import Settings
from exceptions import (
    AppError,
    InvalidUserInputError,
    LLMProviderError,
    TelegramAccessError,
)
from fsm import FSM, FSMContext, FSMState, RedisFSMDispatcher
from llm import LLMProvider


LOGGER = get_logger(component="mainbot")


class MainBot:
    def __init__(
        self,
        config: Settings,
        client: TelegramClient,
        userbot: UserBot,
        fsm: FSM,
        dispatcher: RedisFSMDispatcher,
        llm_provider: LLMProvider,
    ) -> None:
        self._client = client
        self.__token = config.app.token.get_secret_value()
        self._userbot = userbot
        self._fsm = fsm
        self.dispatcher = dispatcher
        self._llm_provider = llm_provider

        self._register_handler()

    async def start_handler(self, event: events.NewMessage.Event, ctx: FSMContext):
        """Хендлер команды /start."""
        await event.reply(
            START_MESSAGE,
            buttons=main_menu(),
        )
        await self._fsm.reset(ctx.key)
        ctx = await self._fsm.get_ctx(ctx.key)

    async def get_messages_limit(self, event: events.NewMessage.Event, ctx: FSMContext):
        """Хендлер состояния wait_channel - получение имени канала."""
        ch = (event.raw_text or "").strip()
        msg = await event.reply(
            get_limit_text(ch), buttons=limit_picker()
        )
        await self._fsm.update_data(ctx, channel=ch, bot_message_id=msg.id)
        await self._fsm.set_state(ctx, FSMState.WAIT_LIMIT)

    async def get_messages_custom_limit(
        self, event: events.NewMessage.Event, ctx: FSMContext
    ):
        """Хендлер состояния wait_custom_limit - ручной ввод лимита."""
        text = (event.raw_text or "").strip()
        try:
            limit = int(text)
            if limit <= 0:
                msg = await event.reply(
                    CUSTOM_LIMIT_ERROR,
                    buttons=cancel_button(),
                )
                await self._fsm.update_data(ctx, bot_message_id=msg.id)
                return

            ch = ctx.data.get("channel")
            await self._parse_and_send(ctx, ch, limit)
        except ValueError:
            msg = await event.reply(
                CUSTOM_LIMIT_ERROR, buttons=cancel_button()
            )
            await self._fsm.update_data(ctx, bot_message_id=msg.id)
            return

    async def _parse_and_send(
        self,
        ctx: FSMContext,
        channel: str,
        limit: int,
    ) -> None:
        """Общий метод для парсинга и отправки результата."""
        bot_msg_id = ctx.data.get("bot_message_id")
        chat_id = ctx.key[0]

        try:
            # Редактируем сообщение бота (показываем загрузку)
            if bot_msg_id:
                await self._client.edit_message(
                    chat_id,
                    bot_msg_id,
                    load_posts_text(limit=limit, channel=channel),
                )
            else:
                # Если ID нет (не должно быть), отправляем новое
                msg = await self._client.send_message(
                    chat_id, load_posts_text(limit=limit, channel=channel)
                )
                bot_msg_id = msg.id

            channel_result = await self._userbot.get_messages(channel, limit)
            LOGGER.info(
                "Получены сообщения: channel={}, count={}",
                channel,
                len(channel_result.messages),
            )

            id_list = [message.id for message in channel_result.messages]
            summary_result = await self._llm_provider.send_message(
                channel_result.messages
            )
            LOGGER.info("Сводка LLM сформирована")
            # Редактируем сообщение с результатом
            await self._client.edit_message(
                chat_id,
                bot_msg_id,
                get_summary_text(
                    ch=channel,
                    id_list=id_list,
                    channel_result=channel_result,
                    summary=summary_result,
                ),
                buttons=action_buttons(),
            )
            await self._fsm.reset(ctx.key)
        except InvalidUserInputError as e:
            await self._handle_parse_error(chat_id, bot_msg_id, e)
            await self._fsm.reset(ctx.key)
        except TelegramAccessError as e:
            await self._handle_parse_error(chat_id, bot_msg_id, e)
            await self._fsm.reset(ctx.key)
        except LLMProviderError as e:
            await self._handle_parse_error(chat_id, bot_msg_id, e)
            await self._fsm.reset(ctx.key)
        except AppError as e:
            await self._handle_parse_error(chat_id, bot_msg_id, e)
            await self._fsm.reset(ctx.key)
        except Exception as e:
            LOGGER.exception("Ошибка при получении сообщений")
            await self._handle_parse_error(chat_id, bot_msg_id, e)
            await self._fsm.reset(ctx.key)

    async def _handle_parse_error(
        self,
        chat_id: int,
        bot_msg_id: int | None,
        error: Exception,
    ) -> None:
        if bot_msg_id:
            await self._client.edit_message(
                chat_id,
                bot_msg_id,
                error_text(error),
                buttons=back_to_menu(),
            )
        else:
            await self._client.send_message(
                chat_id,
                error_text(error),
                buttons=back_to_menu(),
            )

    async def on_message(self, event: events.NewMessage.Event):
        try:
            await self.dispatcher.dispatch(event)
        except Exception:
            LOGGER.exception("FSM handler crashed")

    async def on_callback(self, event: events.CallbackQuery.Event):
        """Обработчик callback-запросов от inline-кнопок."""
        try:
            await self.dispatcher.dispatch_callback(event)
        except Exception:
            LOGGER.exception("Callback handler crashed")

    def _register_handler(self):
        """Регистрирует все хендлеры через единый диспатчер."""
        # Все сообщения идут через диспатчер
        self._client.add_event_handler(
            self.on_message, events.NewMessage(incoming=True)
        )

        # Все callback-запросы идут через диспатчер
        self._client.add_event_handler(self.on_callback, events.CallbackQuery())

        # Регистрируем хендлеры команд в диспатчере
        self.dispatcher.handlers[FSMState.DEFAULT] = self.default_handler
        self.dispatcher.handlers["/start"] = self.start_handler

        # Регистрируем хендлеры состояний FSM
        self.dispatcher.handlers[FSMState.WAIT_CHANNEL] = self.get_messages_limit
        self.dispatcher.handlers[FSMState.WAIT_CUSTOM_LIMIT] = (
            self.get_messages_custom_limit
        )

        # Регистрируем callback-хендлеры
        self.dispatcher.callback_handlers["cmd:get_messages"] = (
            self.callback_get_messages
        )
        self.dispatcher.callback_handlers["cmd:help"] = self.callback_help
        self.dispatcher.callback_handlers["cmd:cancel"] = self.callback_cancel
        self.dispatcher.callback_handlers["cmd:main_menu"] = self.callback_main_menu
        self.dispatcher.callback_handlers["limit:"] = (
            self.callback_limit
        )  # Префикс для всех limit:*

    async def default_handler(self, event: events.NewMessage.Event, ctx: FSMContext):
        """Хендлер по умолчанию для неизвестных команд."""
        await event.reply(
            UNKNOWN_MESSAGE, buttons=main_menu()
        )

    # === Callback handlers ===

    async def callback_get_messages(
        self, event: events.CallbackQuery.Event, ctx: FSMContext
    ):
        """Callback: начать получение сообщений."""
        LOGGER.info(
            "Пользователь запросил получение постов: user_id={}, chat_id={}",
            event.sender_id,
            event.chat_id,
        )
        await event.answer()
        await event.edit(
            WAITING_CHANNEL_MESSAGE,
            buttons=cancel_button(),
        )
        # Сохраняем ID сообщения бота для последующего редактирования
        await self._fsm.update_data(ctx, bot_message_id=event.message_id)
        await self._fsm.set_state(ctx, FSMState.WAIT_CHANNEL)

    async def callback_help(self, event: events.CallbackQuery.Event, ctx: FSMContext):
        """Callback: показать помощь."""
        await event.answer()
        await event.edit(
            HELP_MESSAGE,
            buttons=back_to_menu(),
        )

    async def callback_cancel(self, event: events.CallbackQuery.Event, ctx: FSMContext):
        """Callback: отменить текущее действие."""
        await event.answer("❌ Отменено")
        await self._client.edit_message(
            event.chat_id,
            event.message_id,
            CANCEL_MESSAGE,
            buttons=main_menu(),
        )
        await self._fsm.reset(ctx.key)

    async def callback_main_menu(
        self, event: events.CallbackQuery.Event, ctx: FSMContext
    ):
        """Callback: вернуться в главное меню."""
        await event.answer()
        await self._client.edit_message(
            event.chat_id,
            event.message_id,
            MAIN_MENU_MESSAGE,
            buttons=main_menu(),
        )
        await self._fsm.reset(ctx.key)

    async def callback_limit(self, event: events.CallbackQuery.Event, ctx: FSMContext):
        """Callback: выбор лимита постов."""
        await event.answer()

        callback_data = (
            event.data.decode("utf-8") if isinstance(event.data, bytes) else event.data
        )

        if callback_data == "limit:custom":
            # Пользователь хочет ввести своё значение
            await event.edit(
                CUSTOM_LIMIT_PROMPT, buttons=cancel_button()
            )
            # Сохраняем ID сообщения бота
            await self._fsm.update_data(ctx, bot_message_id=event.message_id)
            await self._fsm.set_state(ctx, FSMState.WAIT_CUSTOM_LIMIT)
        else:
            # Пользователь выбрал предустановленное значение
            limit_str = callback_data.split(":")[1]
            try:
                limit = int(limit_str)
                channel = ctx.data.get("channel")
                # Сохраняем ID перед парсингом
                await self._fsm.update_data(ctx, bot_message_id=event.message_id)
                await self._parse_and_send(ctx, channel, limit)
            except (ValueError, IndexError):
                await event.edit(LIMIT_ERROR_MESSAGE, buttons=back_to_menu())
                await self._fsm.reset(ctx.key)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            LOGGER.info("Shutdown requested")
            loop.create_task(self._shutdown())

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, request_shutdown)
            except NotImplementedError:
                # Some environments (Windows) may not support add_signal_handler for SIGTERM
                pass

        # Запускаем Bot и UserBot
        await self._client.start(bot_token=self.__token)
        await self._userbot.start()

        try:
            await self._client.run_until_disconnected()
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """Graceful shutdown для всех клиентов."""
        LOGGER.info("Shutting down...")

        # Останавливаем UserBot
        try:
            await self._userbot.stop()
        except Exception:
            LOGGER.exception("Error stopping UserBot")

        # Закрываем Bot клиент
        try:
            if self._client.is_connected():
                await self._client.disconnect()
        except Exception:
            LOGGER.exception("Error disconnecting Bot client")
