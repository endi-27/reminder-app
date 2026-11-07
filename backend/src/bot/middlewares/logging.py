import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.core import logger


class BotLoggingMiddleware(BaseMiddleware):
    """
    Проміжний шар (middleware) для структуруваного логування вхідних оновлень Telegram.

    Фіксує ідентифікатор користувача, тип та вміст події і тривалість виконання обробника в мілісекундах.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        event_desc: str = event.__class__.__name__

        if isinstance(event, Message):
            if event.from_user:
                user_id = event.from_user.id
            event_desc = f"Message(text={event.text!r})" if event.text else "Message(non-text)"
        elif isinstance(event, CallbackQuery):
            if event.from_user:
                user_id = event.from_user.id
            event_desc = f"CallbackQuery(data={event.data!r})"
        else:
            from_user = getattr(event, "from_user", None)
            if from_user is not None and hasattr(from_user, "id"):
                user_id = from_user.id

        start_time = time.perf_counter()
        try:
            result = await handler(event, data)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Оброблено подію Telegram: user_id={user_id} event={event_desc} duration_ms={duration_ms:.2f}",
                user_id=user_id,
                event_desc=event_desc,
                duration_ms=duration_ms,
            )
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Помилка під час обробки події Telegram: user_id={user_id} event={event_desc} "
                "duration_ms={duration_ms:.2f} error={error}",
                user_id=user_id,
                event_desc=event_desc,
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise
