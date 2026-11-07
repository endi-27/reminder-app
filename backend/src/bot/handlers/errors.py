from aiogram import Router
from aiogram.types import ErrorEvent, Message

from src.bot.client.exceptions import (
    BotApiConflictError,
    BotApiError,
    BotApiNotFoundError,
    BotApiValidationError,
)
from src.core import logger

errors_router = Router(name="errors")


@errors_router.error()
async def handle_bot_error(event: ErrorEvent) -> bool:
    """
    Глобальний централізований перехоплювач винятків та помилок бекенду.

    Транслює винятки клієнта BotApiError та непередбачені збої у зрозумілі
    повідомлення для користувача українською мовою.
    """
    exc = event.exception
    logger.error(
        "Перехоплено виняток під час обробки оновлення Telegram: {error}",
        error=str(exc),
    )

    if isinstance(exc, BotApiConflictError):
        user_message = "⚠️ Дані були змінені паралельно. Оновіть меню та спробуйте ще раз."
    elif isinstance(exc, BotApiNotFoundError):
        user_message = "⚠️ Запис не знайдено або вже видалено."
    elif isinstance(exc, BotApiValidationError):
        user_message = f"⚠️ Некоректні дані: {exc.message}"
    elif isinstance(exc, BotApiError):
        user_message = "⚠️ Тимчасова помилка зв'язку із сервером. Спробуйте за кілька секунд."
    else:
        user_message = "⚠️ Тимчасова помилка зв'язку із сервером. Спробуйте за кілька секунд."

    # Безпечна відправка відповіді користувачу
    update = event.update
    if update.callback_query is not None:
        try:
            await update.callback_query.answer(text=user_message, show_alert=True)
        except Exception as send_err:
            logger.warning(
                "Не вдалося відповісти на callback_query при обробці помилки: {error}",
                error=str(send_err),
            )
    elif update.message is not None:
        try:
            await update.message.answer(text=user_message)
        except Exception as send_err:
            logger.warning(
                "Не вдалося відправити повідомлення при обробці помилки: {error}",
                error=str(send_err),
            )
    elif hasattr(update, "event") and isinstance(update.event, Message):
        try:
            await update.event.answer(text=user_message)
        except Exception as send_err:
            logger.warning(
                "Не вдалося відправити повідомлення в update.event: {error}",
                error=str(send_err),
            )

    return True
