from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from src.core.config import settings
from src.core.logger import logger
from src.core.protocols import INotificationPublisher
from src.core.redis import RedisClient
from src.infrastructure.notifications.dto import NotificationPayload


class RedisQueuePublisher(INotificationPublisher):
    """
    Реалізація видавця сповіщень у чергу Redis (LPUSH).

    Відправляє повідомлення у чергу, звідки їх вичитує Telegram-бот (BRPOP воркер).
    """

    def __init__(
        self,
        redis_client: RedisClient,
        queue_key: str | None = None,
    ) -> None:
        self._redis = redis_client
        self._queue_key = queue_key or settings.redis.notification_queue_key

    def _serialize_payload(self, payload: NotificationPayload | dict[str, Any] | BaseModel) -> str:
        """Серіалізація об'єкта або словника сповіщення у JSON-рядок."""
        if isinstance(payload, NotificationPayload):
            return payload.model_dump_json()
        if isinstance(payload, BaseModel):
            return payload.model_dump_json()
        if isinstance(payload, dict):
            return NotificationPayload.model_validate(payload).model_dump_json()
        msg = f"Непідтримуваний тип корисного навантаження сповіщення: {type(payload)}"
        raise TypeError(msg)

    async def publish(self, payload: NotificationPayload | dict[str, Any] | BaseModel) -> None:
        """
        Публікація одного сповіщення у чергу Redis.

        Серіалізує об'єкт у JSON та виконує команду LPUSH.
        """
        json_data = self._serialize_payload(payload)
        await self._redis.lpush(self._queue_key, json_data)
        logger.debug(
            "Опубліковано сповіщення у чергу Redis {queue_key}",
            queue_key=self._queue_key,
        )

    async def publish_many(self, payloads: Sequence[NotificationPayload | dict[str, Any] | BaseModel]) -> int:
        """
        Пакетна публікація списку сповіщень у чергу Redis за одну операцію.

        Повертає кількість успішно опублікованих сповіщень.
        """
        if not payloads:
            return 0

        json_items = [self._serialize_payload(p) for p in payloads]
        await self._redis.lpush(self._queue_key, *json_items)
        logger.debug(
            "Опубліковано {count} сповіщень у чергу Redis {queue_key}",
            count=len(json_items),
            queue_key=self._queue_key,
        )
        return len(json_items)
