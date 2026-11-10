import asyncio
from typing import Any

from aiogram import Bot, Dispatcher

from src.bot.bot import BOT_COMMANDS, create_bot, create_dispatcher
from src.bot.client.api_client import BackendApiClient
from src.bot.consumer import RedisNotificationConsumer
from src.core import (
    close_redis,
    get_redis_client,
    logger,
    setup_bot_logging,
    setup_logging,
)
from src.utils import configure_tzdata


async def run_bot(
    bot: Bot | None = None,
    api_client: BackendApiClient | None = None,
    consumer: RedisNotificationConsumer | None = None,
    dp: Dispatcher | None = None,
) -> None:
    """
    Головна точка входу для запуску сервісу Telegram-бота в режимі Long Polling.

    Ініціалізує структуроване логування, екземпляр бота, HTTP-клієнт бекенду,
    диспетчер із роутерами та фоновий споживач черги сповіщень Redis.
    Реєструє хуки життєвого циклу (@dp.startup та @dp.shutdown) та запускає опитування.

    :param bot: Опціональний екземпляр Bot (створюється за замовчуванням через create_bot).
    :param api_client: Опціональний клієнт BackendApiClient.
    :param consumer: Опціональний споживач сповіщень RedisNotificationConsumer.
    :param dp: Опціональний диспетчер Dispatcher.
    """
    try:
        setup_bot_logging()
    except Exception:
        setup_logging()

    configure_tzdata()

    if bot is None:
        bot = create_bot()
    if api_client is None:
        api_client = BackendApiClient()
    if consumer is None:
        redis_client = get_redis_client()
        consumer = RedisNotificationConsumer(bot=bot, redis_client=redis_client)
    if dp is None:
        dp = create_dispatcher(api_client=api_client)

    @dp.startup()
    async def on_startup(*_args: Any, **_kwargs: Any) -> None:
        logger.info("Ініціалізація та запуск сервісу Telegram-бота...")
        try:
            await bot.set_my_commands(BOT_COMMANDS)
            logger.info("Команди меню бота успішно зареєстровано в Telegram")
        except Exception as exc:
            logger.warning(
                "Не вдалося зареєструвати команди меню бота в Telegram: {error}",
                error=str(exc),
            )

        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Вебхук видалено, скинуто очікуючі оновлення (drop_pending_updates=True)")
        except Exception as exc:
            logger.warning(
                "Попередження під час видалення вебхука: {error}",
                error=str(exc),
            )

        await consumer.start()
        logger.info("Фоновий споживач сповіщень Redis успішно запущено")

    @dp.shutdown()
    async def on_shutdown(*_args: Any, **_kwargs: Any) -> None:
        logger.info("Зупинка сервісу Telegram-бота та вивільнення ресурсів...")
        await consumer.stop()
        await api_client.close()
        await close_redis()
        await bot.session.close()
        logger.info("Ресурси Telegram-бота успішно закрито")

    logger.info("Запуск Telegram-бота в режимі Long Polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(run_bot())
