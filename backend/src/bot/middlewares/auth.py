from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.bot.client.api_client import BackendApiClient
from src.core import logger
from src.modules.users.application.dto import RegisterTelegramUserCommand


class BotAuthMiddleware(BaseMiddleware):
    """
    Проміжний шар (middleware) для прозорої аутентифікації користувачів Telegram.

    Синхронізує профіль Telegram з базою даних бекенду та інжектує
    об'єкт current_user і api_client у контекст обробника (data).
    """

    def __init__(self, api_client: BackendApiClient | None = None) -> None:
        self._api_client = api_client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        api_client = self._api_client or data.get("api_client")
        if api_client is None:
            logger.error("BackendApiClient не знайдено в BotAuthMiddleware або контексті data")
            raise RuntimeError("BackendApiClient is required for BotAuthMiddleware")

        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return await handler(event, data)

        chat_id: int = from_user.id
        if isinstance(event, Message):
            if event.chat.type == "private":
                chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message is not None:
            chat = getattr(event.message, "chat", None)
            if chat is not None and getattr(chat, "type", None) == "private":
                chat_id = chat.id

        cmd = RegisterTelegramUserCommand(
            telegram_id=from_user.id,
            telegram_chat_id=chat_id,
            tg_username=from_user.username,
            tg_full_name=from_user.full_name,
        )

        try:
            current_user = await api_client.sync_telegram_user(cmd)
            data["current_user"] = current_user
            data["api_client"] = api_client
        except Exception as exc:
            logger.error(
                "Помилка синхронізації користувача Telegram telegram_id={telegram_id}: {error}",
                telegram_id=from_user.id,
                error=str(exc),
            )
            raise

        return await handler(event, data)
