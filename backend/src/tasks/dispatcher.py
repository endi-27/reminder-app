from typing import Any

from arq import create_pool
from arq.connections import ArqRedis
from arq.connections import RedisSettings as ArqRedisSettings

from src.core import logger, settings


class TaskDispatcher:
    """
    Диспетчер для постановки фонових задач у чергу ARQ з коду додатку.

    Усі публічні методи є строго типізованими обгортками над приватним `_enqueue_task`,
    що унеможливлює використання випадкових текстових назв функцій.
    """

    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        """Отримання або лінива ініціалізація пулу підключень ARQ до Redis."""
        if self._pool is None:
            self._pool = await create_pool(
                ArqRedisSettings(
                    host=settings.redis.host,
                    port=settings.redis.port,
                    password=settings.redis.password,
                    database=settings.redis.databases.task,
                )
            )
        return self._pool

    async def _enqueue_task(self, function_name: str, *args: Any, **kwargs: Any) -> str | None:
        """Внутрішній примітив постановки задачі у чергу ARQ за назвою функції."""
        try:
            pool = await self._get_pool()
            job = await pool.enqueue_job(function_name, *args, _queue_name=settings.arq.queue_name, **kwargs)
            if job:
                logger.info("Задачу {fn} поставлено в чергу ARQ (job_id: {id})", fn=function_name, id=job.job_id)
                return job.job_id
            return None
        except Exception as err:
            logger.error(
                "Не вдалося поставити задачу {function_name} у чергу: {err}",
                function_name=function_name,
                err=str(err),
            )
            return None

    async def enqueue_check_due_reminders(self) -> str | None:
        """Типізована відправка позачергової перевірки нагадувань."""
        from src.tasks.functions.check_due_reminders import cron_check_due_reminders

        return await self._enqueue_task(cron_check_due_reminders.__name__)

    async def enqueue_sync_exchange_rates(self) -> str | None:
        """Типізована відправка позачергової синхронізації курсів валют."""
        from src.tasks.functions.sync_exchange_rates import cron_sync_exchange_rates

        return await self._enqueue_task(cron_sync_exchange_rates.__name__)

    async def enqueue_daily_task_digest(self) -> str | None:
        """Типізована відправка формування щоденного дайджесту."""
        from src.tasks.functions.daily_task_digest import cron_daily_task_digest

        return await self._enqueue_task(cron_daily_task_digest.__name__)

    async def enqueue_check_expiring_trials_and_discounts(self) -> str | None:
        """Типізована відправка перевірки термінів тріалів та знижок."""
        from src.tasks.functions.check_expiring_trials import (
            cron_check_expiring_trials_and_discounts,
        )

        return await self._enqueue_task(cron_check_expiring_trials_and_discounts.__name__)

    async def close(self) -> None:
        """Закриття клієнтського пулу підключень ARQ."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


_global_dispatcher: TaskDispatcher | None = None


def get_task_dispatcher() -> TaskDispatcher:
    """FastAPI Depends провайдер для отримання екземпляра TaskDispatcher."""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = TaskDispatcher()
    return _global_dispatcher


async def close_task_dispatcher() -> None:
    """Закриття глобального екземпляра TaskDispatcher при зупинці додатку."""
    global _global_dispatcher
    if _global_dispatcher is not None:
        await _global_dispatcher.close()
        _global_dispatcher = None
