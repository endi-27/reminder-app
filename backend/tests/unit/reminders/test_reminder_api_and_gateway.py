from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from uuid6 import uuid7

from src.api.main import app
from src.modules.reminders.application.dto import SchedulerBatchResultDTO
from src.modules.reminders.public import RemindersPublicGateway
from tests.unit.fakes import FakeNotificationPublisher, FakeUnitOfWork


@pytest.mark.asyncio
async def test_reminders_public_gateway_transaction_boundary() -> None:
    """
    Тест дотримання Інваріанту 7 (Контроль транзакцій):
    при передачі зовнішнього uow фасад RemindersPublicGateway НЕ викликає commit самостійно.
    """
    external_uow = FakeUnitOfWork()
    mock_session = AsyncMock()
    mock_publisher = FakeNotificationPublisher()

    gateway = RemindersPublicGateway(
        session=mock_session,
        uow=external_uow,
        publisher=mock_publisher,
    )

    # Мокаємо Use Case усередині гейтвею
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = SchedulerBatchResultDTO(
        processed_count=0,
        notifications_queued=0,
        deferred_to_quiet_hours=0,
        completed_or_converted=0,
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.modules.reminders.application.use_cases.process_due_reminders.ProcessDueRemindersUseCase",
            lambda **kwargs: mock_use_case,
        )

        result = await gateway.process_due_reminders()
        assert result.processed_count == 0

        # Перевіряємо, що commit=False було передано в Use Case (Інваріант 7)
        mock_use_case.execute.assert_awaited_once_with(
            now=None,
            batch_size=100,
            commit=False,
        )
        assert external_uow.committed is False


@pytest.mark.asyncio
async def test_reminders_api_auth_protection() -> None:
    """Тест обов'язкової авторизації для ендпоінтів /api/v1/reminders."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Спроба вибірки списку нагадувань без токена
        res_list = await client.get("/api/v1/reminders")
        assert res_list.status_code == 401

        # 2. Спроба створення нагадування без токена
        res_create = await client.post(
            "/api/v1/reminders",
            json={
                "reminder_type": "OPEN_TASK",
                "schedule_logic": "DAILY_AT_TIMES",
                "title": "Справа",
                "schedule_config": {"times": ["09:00:00"]},
            },
        )
        assert res_create.status_code == 401

        # 3. Спроба видалення без токена
        res_del = await client.delete(f"/api/v1/reminders/{uuid7()}")
        assert res_del.status_code == 401
