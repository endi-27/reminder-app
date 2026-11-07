from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from src.bot.client.api_client import BackendApiClient
from src.bot.handlers import setup_routers
from src.bot.middlewares import BotAuthMiddleware, BotLoggingMiddleware
from src.core import get_redis_client, settings

BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Головне меню та перезапуск"),
    BotCommand(command="new", description="Створити нове нагадування"),
    BotCommand(command="list", description="Мої нагадування та фільтри"),
    BotCommand(command="rates", description="Актуальні курси валют банків"),
    BotCommand(command="settings", description="Налаштування профілю та банку"),
    BotCommand(command="cancel", description="Скасувати поточну дію"),
    BotCommand(command="help", description="Довідка по роботі з ботом"),
]


def create_bot(token: str | None = None) -> Bot:
    """
    Створює екземпляр Telegram Bot із налаштованим режимом форматування HTML.

    :param token: Токен бота від BotFather (якщо None, береться з конфігурації settings.bot.token).
    :return: Налаштований екземпляр aiogram.Bot.
    """
    return Bot(
        token=token or settings.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(
    storage: BaseStorage | None = None,
    api_client: BackendApiClient | None = None,
) -> Dispatcher:
    """
    Створює та конфігурує головний диспетчер бота (Dispatcher).

    Якщо сховище FSM storage не передано, створюється RedisStorage з префіксом 'fsm'.
    Реєструє зовнішні мідлварі логування (BotLoggingMiddleware) та автентифікації (BotAuthMiddleware),
    а також підключає всі модульні роутери системи.

    :param storage: Сховище станів FSM (за замовчуванням RedisStorage).
    :param api_client: Клієнт взаємодії з бекендом для передачі в BotAuthMiddleware.
    :return: Готовий екземпляр Dispatcher.
    """
    if storage is None:
        redis_client = get_redis_client()
        key_builder = DefaultKeyBuilder(prefix="fsm", with_bot_id=True, with_destiny=True)
        storage = RedisStorage(
            redis=redis_client,
            key_builder=key_builder,
            state_ttl=3600,
            data_ttl=3600,
        )

    dp = Dispatcher(storage=storage)

    if api_client is not None:
        dp["api_client"] = api_client

    logging_middleware = BotLoggingMiddleware()
    auth_middleware = BotAuthMiddleware(api_client=api_client)

    dp.message.outer_middleware(logging_middleware)
    dp.message.outer_middleware(auth_middleware)
    dp.callback_query.outer_middleware(logging_middleware)
    dp.callback_query.outer_middleware(auth_middleware)

    setup_routers(dp)

    return dp
