from typing import Any

from src.core import get_redis_client, logger
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications import RedisQueuePublisher
from src.modules.reminders.public import RemindersPublicGateway


async def cron_check_due_reminders(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Щохвилинна періодична задача ARQ для перевірки та відправки чергових нагадувань.

    Отримує чергові активні нагадування з БД, розраховує наступний тригер або завершує їх,
    ескалує пріоритет за потреби та пушить повідомлення у чергу Redis для бота.
    """
    logger.info("Початок виконання періодичної задачі перевірки чергових нагадувань.")

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
        batch_result = await gateway.process_due_reminders()
        await uow.commit()

    logger.info(
        "Завершено перевірку нагадувань: оброблено {total}, у черзі {queued}, "
        "відкладено (тихі години) {deferred}, завершено/конвертовано {completed}",
        total=batch_result.processed_count,
        queued=batch_result.notifications_queued,
        deferred=batch_result.deferred_to_quiet_hours,
        completed=batch_result.completed_or_converted,
    )
    return batch_result.model_dump()
