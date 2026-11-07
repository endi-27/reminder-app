import asyncio
import contextlib
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from pydantic import ValidationError

from src.bot.formatters.messages import format_notification_payload
from src.bot.keyboards.inline_reminders import build_notification_keyboard
from src.core import logger
from src.core.config import settings
from src.core.redis import RedisClient
from src.infrastructure.notifications.dto import NotificationPayload


class RedisNotificationConsumer:
    """
    Фоновий споживач черги сповіщень Redis (BRPOP queue:notifications:telegram).

    Вичитує серіалізовані об'єкти NotificationPayload, формує клавіатури дій
    та надсилає сповіщення користувачам через Telegram Bot API з обробкою лімітів (Flood Wait)
    та відмовостійким поверненням у чергу при мережевих збоях.
    """

    def __init__(
        self,
        bot: Bot,
        redis_client: RedisClient,
        queue_key: str | None = None,
        brpop_timeout: int = 2,
    ) -> None:
        self._bot = bot
        self._redis = redis_client
        self._queue_key = queue_key or settings.redis.notification_queue_key
        self._brpop_timeout = brpop_timeout
        self._running: bool = False
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        """Перевірка активності споживача."""
        return self._running

    async def process_one(self, raw_payload: str) -> bool:
        """
        Обробка та надсилання одного сповіщення з черги.

        Повертає True, якщо сповіщення доставлено успішно, або False при помилці чи блокуванні.
        """
        try:
            payload = NotificationPayload.model_validate_json(raw_payload)
        except (ValidationError, ValueError) as exc:
            logger.error(
                "Помилка десеріалізації NotificationPayload: {error}. Сирі дані: {payload}",
                error=str(exc),
                payload=raw_payload,
            )
            return False

        text = format_notification_payload(payload)
        keyboard = build_notification_keyboard(payload)

        try:
            await self._bot.send_message(
                chat_id=payload.recipient_chat_id,
                text=text,
                reply_markup=keyboard,
                disable_notification=payload.disable_sound,
            )
            logger.info(
                "Сповіщення успішно надіслано користувачу chat_id={chat_id}",
                chat_id=payload.recipient_chat_id,
            )
            return True

        except TelegramRetryAfter as exc:
            logger.warning(
                "Telegram Flood Wait: пауза {seconds} с перед повторною спробою надсилання...",
                seconds=exc.retry_after,
            )
            await asyncio.sleep(exc.retry_after)
            try:
                await self._bot.send_message(
                    chat_id=payload.recipient_chat_id,
                    text=text,
                    reply_markup=keyboard,
                    disable_notification=payload.disable_sound,
                )
                logger.info(
                    "Сповіщення успішно надіслано після паузи Flood Wait (chat_id={chat_id})",
                    chat_id=payload.recipient_chat_id,
                )
                return True
            except Exception as retry_exc:
                logger.error(
                    "Помилка повторного надсилання після Flood Wait: {error}",
                    error=str(retry_exc),
                )
                return False

        except TelegramForbiddenError as exc:
            logger.warning(
                "Користувач {chat_id} заблокував бота або чат недоступний: {error}",
                chat_id=payload.recipient_chat_id,
                error=str(exc),
            )
            return False

        except (TelegramNetworkError, TelegramServerError) as exc:
            logger.error(
                "Мережева або серверна помилка Telegram: {error}. Повернення сповіщення у чергу...",
                error=str(exc),
            )
            await self._redis.rpush(self._queue_key, raw_payload)
            await asyncio.sleep(2)
            return False

        except Exception as exc:
            logger.exception(
                "Неочікувана помилка надсилання сповіщення: {error}",
                error=str(exc),
            )
            return False

    async def start(self) -> None:
        """Запуск фонового асинхронного циклу зчитування сповіщень."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="redis_notification_consumer")
        logger.info(
            "Запущено фоновий споживач сповіщень Redis для черги: {queue}",
            queue=self._queue_key,
        )

    async def stop(self) -> None:
        """Зупинка фонового споживача та очікування завершення поточної ітерації."""
        if not self._running:
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        logger.info("Зупинено фоновий споживач сповіщень Redis.")

    async def _run_loop(self) -> None:
        """Внутрішній асинхронний цикл очікування нових сповіщень у черзі Redis."""
        while self._running:
            try:
                result: Any = await self._redis.brpop([self._queue_key], timeout=self._brpop_timeout)
                if result is None:
                    continue

                _, raw_payload = result
                await self.process_one(raw_payload)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Неочікувана помилка в циклі зчитування з черги Redis: {error}",
                    error=str(exc),
                )
                await asyncio.sleep(1)
