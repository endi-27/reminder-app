from typing import Any

from src.core import get_redis_client, logger
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications import RedisQueuePublisher
from src.modules.reminders.public import RemindersPublicGateway


async def cron_check_expiring_trials_and_discounts(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Щоденна періодична задача ARQ для перевірки закінчення пробних періодів та знижок підписок.

    Знаходить підписки, у яких незабаром завершується безкоштовний пробний період (TRIAL)
    або спливають цикли дії знижки, і відправляє завчасне попередження користувачу.
    """
    logger.info("Початок перевірки закінчення пробних періодів та знижок для підписок.")

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
        notified_count = await gateway.check_expiring_trials_and_discounts()
        await uow.commit()

    logger.info(
        "Завершено перевірку тріалів та знижок: відправлено попереджень {count}",
        count=notified_count,
    )
    return {"notified": notified_count}
