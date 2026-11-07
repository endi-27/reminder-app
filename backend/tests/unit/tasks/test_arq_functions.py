from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.finance.application.dto import SyncRatesResultDTO
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.reminders.application.dto import SchedulerBatchResultDTO
from src.tasks.cron import CRON_JOBS
from src.tasks.dispatcher import (
    TaskDispatcher,
    close_task_dispatcher,
    get_task_dispatcher,
)
from src.tasks.functions import (
    cron_check_due_reminders,
    cron_check_expiring_trials_and_discounts,
    cron_daily_task_digest,
    cron_sync_exchange_rates,
)
from src.tasks.worker import WorkerSettings, shutdown, startup


class FakeUnitOfWork:
    """Фейковий Unit of Work для перевірки відкриття контексту та фіксації транзакцій."""

    def __init__(self) -> None:
        self.session = MagicMock()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.asyncio
async def test_cron_check_due_reminders_success() -> None:
    """Перевірка успішного виконання щохвилинної періодичної задачі чергових нагадувань."""
    fake_uow = FakeUnitOfWork()
    mock_batch_result = SchedulerBatchResultDTO(
        processed_count=5,
        notifications_queued=4,
        deferred_to_quiet_hours=1,
        completed_or_converted=0,
    )
    mock_redis = MagicMock()

    with (
        patch("src.tasks.functions.check_due_reminders.SqlAlchemyUnitOfWork", return_value=fake_uow),
        patch(
            "src.tasks.functions.check_due_reminders.RemindersPublicGateway.process_due_reminders",
            new_callable=AsyncMock,
            return_value=mock_batch_result,
        ) as mock_process,
    ):
        result = await cron_check_due_reminders(ctx={"redis": mock_redis})

    assert fake_uow.committed is True
    mock_process.assert_awaited_once()
    assert result == {
        "processed_count": 5,
        "notifications_queued": 4,
        "deferred_to_quiet_hours": 1,
        "completed_or_converted": 0,
    }


@pytest.mark.asyncio
async def test_cron_check_due_reminders_fallback_redis() -> None:
    """Перевірка фолбеку на глобальний Redis-клієнт, якщо його немає в ctx."""
    fake_uow = FakeUnitOfWork()
    mock_batch_result = SchedulerBatchResultDTO(
        processed_count=0,
        notifications_queued=0,
        deferred_to_quiet_hours=0,
        completed_or_converted=0,
    )

    with (
        patch("src.tasks.functions.check_due_reminders.SqlAlchemyUnitOfWork", return_value=fake_uow),
        patch("src.tasks.functions.check_due_reminders.get_redis_client", return_value=MagicMock()) as mock_get_redis,
        patch(
            "src.tasks.functions.check_due_reminders.RemindersPublicGateway.process_due_reminders",
            new_callable=AsyncMock,
            return_value=mock_batch_result,
        ),
    ):
        await cron_check_due_reminders(ctx={})

    mock_get_redis.assert_called_once()
    assert fake_uow.committed is True


@pytest.mark.asyncio
async def test_cron_sync_exchange_rates_success() -> None:
    """Перевірка успішної синхронізації курсів валют із банківських API."""
    fake_uow = FakeUnitOfWork()
    mock_sync_result = SyncRatesResultDTO(
        synced_count=3,
        providers_succeeded=[ExchangeRateProvider.NBU, ExchangeRateProvider.MONOBANK],
        providers_failed={},
    )

    with (
        patch("src.tasks.functions.sync_exchange_rates.SqlAlchemyUnitOfWork", return_value=fake_uow),
        patch(
            "src.tasks.functions.sync_exchange_rates.FinancePublicGateway.sync_all_rates",
            new_callable=AsyncMock,
            return_value=mock_sync_result,
        ) as mock_sync,
    ):
        result = await cron_sync_exchange_rates(ctx={})

    assert fake_uow.committed is True
    mock_sync.assert_awaited_once()
    assert result["synced_count"] == 3
    assert ExchangeRateProvider.NBU in result["providers_succeeded"]


@pytest.mark.asyncio
async def test_cron_daily_task_digest_success() -> None:
    """Перевірка відправки щоденного дайджесту відкритих задач."""
    fake_uow = FakeUnitOfWork()
    mock_redis = MagicMock()

    with (
        patch("src.tasks.functions.daily_task_digest.SqlAlchemyUnitOfWork", return_value=fake_uow),
        patch(
            "src.tasks.functions.daily_task_digest.RemindersPublicGateway.process_daily_digest",
            new_callable=AsyncMock,
            return_value=7,
        ) as mock_digest,
    ):
        result = await cron_daily_task_digest(ctx={"redis": mock_redis})

    assert fake_uow.committed is True
    mock_digest.assert_awaited_once()
    assert result == {"digests_sent": 7}


@pytest.mark.asyncio
async def test_cron_check_expiring_trials_and_discounts_success() -> None:
    """Перевірка моніторингу закінчення тріалів та знижок підписок."""
    fake_uow = FakeUnitOfWork()
    mock_redis = MagicMock()

    with (
        patch("src.tasks.functions.check_expiring_trials.SqlAlchemyUnitOfWork", return_value=fake_uow),
        patch(
            "src.tasks.functions.check_expiring_trials.RemindersPublicGateway.check_expiring_trials_and_discounts",
            new_callable=AsyncMock,
            return_value=3,
        ) as mock_check,
    ):
        result = await cron_check_expiring_trials_and_discounts(ctx={"redis": mock_redis})

    assert fake_uow.committed is True
    mock_check.assert_awaited_once()
    assert result == {"notified": 3}


@pytest.mark.asyncio
async def test_worker_settings_and_lifecycle() -> None:
    """Перевірка параметрів воркера ARQ та хуків життєвого циклу startup/shutdown."""
    assert len(WorkerSettings.functions) == 4
    assert len(WorkerSettings.cron_jobs) == 4
    assert WorkerSettings.cron_jobs == CRON_JOBS

    ctx: dict[str, Any] = {}
    with (
        patch("src.tasks.worker.setup_worker_logging") as mock_setup_log,
        patch("src.tasks.worker.get_redis_client", return_value="fake_redis_client"),
    ):
        await startup(ctx)

    mock_setup_log.assert_called_once()
    assert ctx["redis"] == "fake_redis_client"

    with (
        patch("src.tasks.worker.close_redis", new_callable=AsyncMock) as mock_close_redis,
        patch("src.tasks.worker.close_db", new_callable=AsyncMock) as mock_close_db,
    ):
        await shutdown(ctx)

    mock_close_redis.assert_awaited_once()
    mock_close_db.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_dispatcher_lifecycle_and_enqueue() -> None:
    """Перевірка типізованих методів диспетчера задач TaskDispatcher."""
    dispatcher = TaskDispatcher()
    mock_pool = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "test-job-uuid-123"
    mock_pool.enqueue_job = AsyncMock(return_value=mock_job)
    mock_pool.close = AsyncMock()

    with patch.object(dispatcher, "_get_pool", AsyncMock(return_value=mock_pool)):
        job_id_1 = await dispatcher.enqueue_check_due_reminders()
        job_id_2 = await dispatcher.enqueue_sync_exchange_rates()
        job_id_3 = await dispatcher.enqueue_daily_task_digest()
        job_id_4 = await dispatcher.enqueue_check_expiring_trials_and_discounts()

    assert job_id_1 == "test-job-uuid-123"
    assert job_id_2 == "test-job-uuid-123"
    assert job_id_3 == "test-job-uuid-123"
    assert job_id_4 == "test-job-uuid-123"
    assert mock_pool.enqueue_job.await_count == 4

    # Перевірка поведінки при помилці постановки в чергу
    with patch.object(dispatcher, "_get_pool", AsyncMock(side_effect=RuntimeError("Redis down"))):
        failed_id = await dispatcher.enqueue_check_due_reminders()
        assert failed_id is None

    # Перевірка закриття пулу
    dispatcher._pool = mock_pool
    await dispatcher.close()
    mock_pool.close.assert_awaited_once()
    assert dispatcher._pool is None

    # Перевірка глобальних функцій DI
    d1 = get_task_dispatcher()
    d2 = get_task_dispatcher()
    assert d1 is d2
    await close_task_dispatcher()
