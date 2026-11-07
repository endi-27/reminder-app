from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from src.bot.bot import (
    BOT_COMMANDS,
    create_bot,
    create_dispatcher,
)
from src.bot.client.api_client import BackendApiClient
from src.bot.consumer import RedisNotificationConsumer
from src.bot.main import (
    run_bot,
)
from src.bot.middlewares import BotAuthMiddleware, BotLoggingMiddleware
from src.core import settings


def test_bot_commands_list() -> None:
    """Перевірка наявності 7 канонічних команд бота з українськими описами."""
    assert len(BOT_COMMANDS) == 7

    expected_commands: dict[str, str] = {
        "start": "Головне меню та перезапуск",
        "new": "Створити нове нагадування",
        "list": "Мої нагадування та фільтри",
        "rates": "Актуальні курси валют банків",
        "settings": "Налаштування профілю та банку",
        "cancel": "Скасувати поточну дію",
        "help": "Довідка по роботі з ботом",
    }

    commands_dict = {cmd.command: cmd.description for cmd in BOT_COMMANDS}
    assert commands_dict == expected_commands


def test_create_bot_with_custom_token() -> None:
    """Перевірка ініціалізації бота з кастомним валідним токеном та ParseMode.HTML."""
    fake_token = "123456789:AAE_fake_token_for_unit_tests_12345"
    bot = create_bot(token=fake_token)

    assert bot.token == fake_token
    assert bot.default is not None
    assert bot.default.parse_mode == ParseMode.HTML


def test_create_bot_with_default_token() -> None:
    """Перевірка ініціалізації бота за замовчуванням із токеном з конфігурації settings."""
    bot = create_bot()

    assert bot.token == settings.bot.token
    assert bot.default is not None
    assert bot.default.parse_mode == ParseMode.HTML


def test_create_dispatcher_with_memory_storage() -> None:
    """Перевірка конфігурації диспетчера з MemoryStorage, реєстрації 7 роутерів та зовнішніх мідлварей."""
    storage = MemoryStorage()
    mock_api_client = MagicMock(spec=BackendApiClient)

    dp = create_dispatcher(storage=storage, api_client=mock_api_client)

    assert dp.storage is storage
    assert dp["api_client"] is mock_api_client
    assert len(dp.sub_routers) == 7

    # Перевірка зовнішніх мідлварей на message
    assert len(dp.message.outer_middleware) == 2
    assert isinstance(dp.message.outer_middleware[0], BotLoggingMiddleware)
    assert isinstance(dp.message.outer_middleware[1], BotAuthMiddleware)

    # Перевірка зовнішніх мідлварей на callback_query
    assert len(dp.callback_query.outer_middleware) == 2
    assert isinstance(dp.callback_query.outer_middleware[0], BotLoggingMiddleware)
    assert isinstance(dp.callback_query.outer_middleware[1], BotAuthMiddleware)


def test_create_dispatcher_default_redis_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Перевірка створення RedisStorage за замовчуванням, якщо storage не передано."""
    mock_redis = MagicMock()
    monkeypatch.setattr("src.bot.bot.get_redis_client", lambda: mock_redis)

    dp = create_dispatcher()

    assert isinstance(dp.storage, RedisStorage)
    assert dp.storage.redis is mock_redis


@pytest.mark.asyncio
async def test_run_bot_lifecycle_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Перевірка успішного виконання startup та shutdown хуків у run_bot."""
    mock_bot = MagicMock(spec=Bot)
    mock_bot.set_my_commands = AsyncMock()
    mock_bot.delete_webhook = AsyncMock()
    mock_bot.session = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_api_client = MagicMock(spec=BackendApiClient)
    mock_api_client.close = AsyncMock()

    mock_consumer = MagicMock(spec=RedisNotificationConsumer)
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()

    mock_close_redis = AsyncMock()
    monkeypatch.setattr("src.bot.main.close_redis", mock_close_redis)

    dp = Dispatcher(storage=MemoryStorage())

    async def fake_start_polling(bot: Bot, **_kwargs: object) -> None:
        await dp.emit_startup()
        await dp.emit_shutdown()

    monkeypatch.setattr(dp, "start_polling", fake_start_polling)

    await run_bot(
        bot=mock_bot,
        api_client=mock_api_client,
        consumer=mock_consumer,
        dp=dp,
    )

    # Перевірка викликів хука startup
    mock_bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    mock_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    mock_consumer.start.assert_awaited_once()

    # Перевірка викликів хука shutdown
    mock_consumer.stop.assert_awaited_once()
    mock_api_client.close.assert_awaited_once()
    mock_close_redis.assert_awaited_once()
    mock_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bot_startup_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Перевірка стійкості хука startup при виникненні помилок у Telegram API (не фатальні)."""
    mock_bot = MagicMock(spec=Bot)
    mock_bot.set_my_commands = AsyncMock(side_effect=Exception("Помилка реєстрації команд"))
    mock_bot.delete_webhook = AsyncMock(side_effect=Exception("Помилка видалення вебхука"))
    mock_bot.session = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_api_client = MagicMock(spec=BackendApiClient)
    mock_api_client.close = AsyncMock()

    mock_consumer = MagicMock(spec=RedisNotificationConsumer)
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()

    mock_close_redis = AsyncMock()
    monkeypatch.setattr("src.bot.main.close_redis", mock_close_redis)

    dp = Dispatcher(storage=MemoryStorage())

    async def fake_start_polling(bot: Bot, **_kwargs: object) -> None:
        await dp.emit_startup()
        await dp.emit_shutdown()

    monkeypatch.setattr(dp, "start_polling", fake_start_polling)

    # Виконання не повинно викликати виняток
    await run_bot(
        bot=mock_bot,
        api_client=mock_api_client,
        consumer=mock_consumer,
        dp=dp,
    )

    mock_bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    mock_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    mock_consumer.start.assert_awaited_once()
    mock_consumer.stop.assert_awaited_once()
    mock_api_client.close.assert_awaited_once()
    mock_close_redis.assert_awaited_once()
    mock_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bot_default_instantiation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Перевірка створення компонентів за замовчуванням при виклику run_bot() без аргументів."""
    mock_bot = MagicMock(spec=Bot)
    mock_bot.set_my_commands = AsyncMock()
    mock_bot.delete_webhook = AsyncMock()
    mock_bot.session = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_api_client = MagicMock(spec=BackendApiClient)
    mock_api_client.close = AsyncMock()

    mock_consumer = MagicMock(spec=RedisNotificationConsumer)
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()

    mock_redis = MagicMock()
    mock_close_redis = AsyncMock()

    dp = Dispatcher(storage=MemoryStorage())

    async def fake_start_polling(bot: Bot, **_kwargs: object) -> None:
        await dp.emit_startup()
        await dp.emit_shutdown()

    monkeypatch.setattr(dp, "start_polling", fake_start_polling)

    monkeypatch.setattr("src.bot.main.create_bot", lambda: mock_bot)
    monkeypatch.setattr("src.bot.main.BackendApiClient", lambda: mock_api_client)
    monkeypatch.setattr("src.bot.main.get_redis_client", lambda: mock_redis)
    monkeypatch.setattr("src.bot.main.RedisNotificationConsumer", lambda bot, redis_client: mock_consumer)
    monkeypatch.setattr("src.bot.main.create_dispatcher", lambda api_client: dp)
    monkeypatch.setattr("src.bot.main.close_redis", mock_close_redis)

    await run_bot()

    mock_bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    mock_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    mock_consumer.start.assert_awaited_once()
    mock_consumer.stop.assert_awaited_once()
    mock_api_client.close.assert_awaited_once()
    mock_close_redis.assert_awaited_once()
    mock_bot.session.close.assert_awaited_once()
