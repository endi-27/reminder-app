from typing import Any

from arq.connections import RedisSettings as ArqRedisSettings

# Реєстрація всіх ORM-моделей у Base.metadata для фонового воркера
import src.modules.finance.infrastructure.models  # noqa: F401
import src.modules.reminders.infrastructure.models  # noqa: F401
import src.modules.users.infrastructure.models  # noqa: F401
from src.core import close_db, close_redis, get_redis_client, logger, settings, setup_worker_logging
from src.tasks.cron import CRON_JOBS
from src.tasks.functions import (
    cron_check_due_reminders,
    cron_check_expiring_trials_and_discounts,
    cron_daily_task_digest,
    cron_sync_exchange_rates,
)
from src.utils import configure_tzdata


async def startup(ctx: dict[str, Any]) -> None:
    """Хук запуску фонового воркера ARQ: ініціалізація логування та клієнтів."""
    setup_worker_logging()
    configure_tzdata()
    ctx["redis"] = get_redis_client()
    logger.info(
        "[ARQ Worker] Воркер успішно запущено. Черга: {queue} | Максимум паралельних задач: {max_jobs}",
        queue=settings.arq.queue_name,
        max_jobs=settings.arq.max_jobs,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    """Хук безпечної зупинки фонового воркера ARQ: вивільнення пулів Redis та БД."""
    await close_redis()
    await close_db()
    logger.info("[ARQ Worker] Воркер успішно зупинено. Ресурси БД та Redis вивільнено.")


class WorkerSettings:
    """Конфігурація запуску воркера ARQ."""

    functions = [
        cron_check_due_reminders,
        cron_sync_exchange_rates,
        cron_daily_task_digest,
        cron_check_expiring_trials_and_discounts,
    ]

    cron_jobs = CRON_JOBS

    on_startup = startup
    on_shutdown = shutdown

    max_tries = settings.arq.max_tries
    max_jobs = settings.arq.max_jobs
    job_timeout = settings.arq.job_timeout
    keep_result = settings.arq.keep_result
    health_check_interval = settings.arq.health_check_interval
    queue_name = settings.arq.queue_name

    redis_settings = ArqRedisSettings(
        host=settings.redis.host,
        port=settings.redis.port,
        password=settings.redis.password,
        database=settings.redis.databases.task,
    )


if __name__ == "__main__":
    from typing import cast

    from arq import run_worker

    run_worker(cast(Any, WorkerSettings))
