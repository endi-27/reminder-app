from typing import Any

from src.core import get_redis_client, logger
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications import RedisQueuePublisher
from src.modules.reminders.public import RemindersPublicGateway


async def cron_daily_task_digest(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Періодична задача ARQ для формування та відправки щоденного дайджесту відкритих задач.

    Формує для користувачів зведення актуальних відкритих задач з високим пріоритетом
    відповідно до їхнього локального часу та налаштованого інтервалу дайджесту.
    """
    logger.info("Початок виконання періодичної задачі щоденного дайджесту задач.")

    redis_client = ctx.get("redis")
    if redis_client is None:
        redis_client = get_redis_client()

    publisher = RedisQueuePublisher(redis_client=redis_client)

    async with SqlAlchemyUnitOfWork() as uow:
        gateway = RemindersPublicGateway(
            session=uow.session,
            uow=uow,
            publisher=publisher,
        )
        sent_count = await gateway.process_daily_digest()
        await uow.commit()

    logger.info("Завершено формування щоденного дайджесту: надіслано повідомлень {count}", count=sent_count)
    return {"digests_sent": sent_count}
