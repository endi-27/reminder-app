import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.base import NO_VALUE
from uuid6 import uuid7

from src.infrastructure.db.inspection import get_loaded, is_loaded
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications.dto import (
    DigestTaskItemDTO,
    NotificationEventType,
    NotificationPayload,
)
from src.infrastructure.notifications.redis_queue_publisher import RedisQueuePublisher
from src.modules.reminders.domain.enums import CurrencyCode, Priority, ReminderType


class TestNotificationDTOs:
    """Тести валідації та серіалізації DTO сповіщень."""

    def test_notification_event_type_enum(self) -> None:
        """Перевірка значень переліку NotificationEventType."""
        assert NotificationEventType.REMINDER_DUE == "REMINDER_DUE"
        assert NotificationEventType.TRIAL_EXPIRED == "TRIAL_EXPIRED"
        assert NotificationEventType.DAILY_DIGEST == "DAILY_DIGEST"

    def test_digest_task_item_dto_valid(self) -> None:
        """Перевірка успішного створення елемента дайджесту зі валідними даними."""
        task_id = uuid7()
        item = DigestTaskItemDTO(
            reminder_id=task_id,
            title="Купити молоко",
            description="2.5% жирності",
            priority=Priority.HIGH,
        )
        assert item.reminder_id == task_id
        assert item.title == "Купити молоко"
        assert item.description == "2.5% жирності"
        assert item.priority == Priority.HIGH

    def test_digest_task_item_dto_defaults(self) -> None:
        """Перевірка значень за замовчуванням для DigestTaskItemDTO."""
        task_id = uuid7()
        item = DigestTaskItemDTO(
            reminder_id=task_id,
            title="Зателефонувати лікарю",
        )
        assert item.description is None
        assert item.priority is None

    def test_digest_task_item_dto_validation_errors(self) -> None:
        """Перевірка обмежень довжини назви задачі в дайджесті."""
        task_id = uuid7()
        with pytest.raises(ValidationError):
            DigestTaskItemDTO(reminder_id=task_id, title="")

        with pytest.raises(ValidationError):
            DigestTaskItemDTO(reminder_id=task_id, title="A" * 256)

    def test_notification_payload_valid_and_defaults(self) -> None:
        """Перевірка створення корисного навантаження сповіщення та значень за замовчуванням."""
        reminder_id = uuid7()
        payload = NotificationPayload(
            recipient_chat_id=123456789,
            reminder_id=reminder_id,
            reminder_type=ReminderType.MEDICATION,
            title="Прийом ліків",
            description="Час прийняти Омега-3",
        )

        assert payload.event_type == NotificationEventType.REMINDER_DUE
        assert payload.recipient_channel == "telegram"
        assert payload.recipient_chat_id == 123456789
        assert payload.user_timezone == "Europe/Kyiv"
        assert payload.disable_sound is False
        assert payload.reminder_id == reminder_id
        assert payload.reminder_type == ReminderType.MEDICATION
        assert payload.title == "Прийом ліків"
        assert payload.description == "Час прийняти Омега-3"
        assert payload.due_datetime is None
        assert payload.effective_priority is None
        assert payload.amount is None
        assert payload.currency is None
        assert payload.converted_amount_uah is None
        assert payload.rate_provider is None
        assert payload.is_stale_rate_fallback is False
        assert payload.is_trial is False
        assert payload.is_last_discount_cycle is False
        assert payload.medication_end_date is None
        assert payload.strict_schedule is False
        assert payload.calculated_age is None
        assert payload.digest_tasks == []

        # Перевірка серіалізації в JSON
        json_data = json.loads(payload.model_dump_json())
        assert json_data["event_type"] == "REMINDER_DUE"
        assert json_data["recipient_channel"] == "telegram"
        assert json_data["recipient_chat_id"] == 123456789
        assert json_data["reminder_id"] == str(reminder_id)
        assert json_data["reminder_type"] == "MEDICATION"
        assert json_data["title"] == "Прийом ліків"
        assert json_data["digest_tasks"] == []

    def test_notification_payload_full_attributes_serialization(self) -> None:
        """Перевірка повної серіалізації всіх полів різних типів подій сповіщень."""
        reminder_id = uuid7()
        task_item = DigestTaskItemDTO(reminder_id=uuid7(), title="Задача 1", priority=Priority.LOW)
        payload = NotificationPayload(
            event_type=NotificationEventType.DAILY_DIGEST,
            recipient_chat_id=987654321,
            reminder_id=reminder_id,
            amount=Decimal("199.99"),
            currency=CurrencyCode.USD,
            converted_amount_uah=Decimal("8300.00"),
            rate_provider="MONOBANK",
            is_stale_rate_fallback=True,
            is_trial=True,
            is_last_discount_cycle=True,
            medication_end_date=date(2026, 12, 31),
            strict_schedule=True,
            calculated_age=30,
            digest_tasks=[task_item],
        )

        json_str = payload.model_dump_json()
        deserialized = NotificationPayload.model_validate_json(json_str)

        assert deserialized.event_type == NotificationEventType.DAILY_DIGEST
        assert deserialized.recipient_chat_id == 987654321
        assert deserialized.reminder_id == reminder_id
        assert deserialized.amount == Decimal("199.99")
        assert deserialized.currency == CurrencyCode.USD
        assert deserialized.converted_amount_uah == Decimal("8300.00")
        assert deserialized.rate_provider == "MONOBANK"
        assert deserialized.is_stale_rate_fallback is True
        assert deserialized.is_trial is True
        assert deserialized.is_last_discount_cycle is True
        assert deserialized.medication_end_date == date(2026, 12, 31)
        assert deserialized.strict_schedule is True
        assert deserialized.calculated_age == 30
        assert len(deserialized.digest_tasks) == 1
        assert deserialized.digest_tasks[0].title == "Задача 1"

    def test_notification_payload_validation_errors(self) -> None:
        """Перевірка обов'язковості recipient_chat_id у NotificationPayload."""
        with pytest.raises(ValidationError):
            NotificationPayload()  # type: ignore[call-arg]


class TestRedisQueuePublisher:
    """Тести для паблішера сповіщень у чергу Redis."""

    @pytest.mark.asyncio
    async def test_publish_payload_success(self) -> None:
        """Перевірка публікації об'єкта NotificationPayload у Redis."""
        mock_redis = AsyncMock()
        publisher = RedisQueuePublisher(redis_client=mock_redis)

        reminder_id = uuid7()
        payload = NotificationPayload(
            recipient_chat_id=987654321,
            reminder_id=reminder_id,
            title="Тестове нагадування",
            description="Опис події",
        )

        await publisher.publish(payload)

        mock_redis.lpush.assert_awaited_once()
        args, _ = mock_redis.lpush.await_args
        queue_key, json_str = args
        assert queue_key == "queue:notifications:telegram"
        parsed = json.loads(json_str)
        assert parsed["recipient_chat_id"] == 987654321
        assert parsed["reminder_id"] == str(reminder_id)
        assert parsed["title"] == "Тестове нагадування"
        assert parsed["event_type"] == "REMINDER_DUE"

    @pytest.mark.asyncio
    async def test_publish_dict_payload_success(self) -> None:
        """Перевірка публікації сповіщення, переданого як валідний словник dict."""
        mock_redis = AsyncMock()
        publisher = RedisQueuePublisher(redis_client=mock_redis, queue_key="custom:queue")

        raw_dict = {
            "recipient_chat_id": 555666777,
            "title": "Зі словника",
            "description": "Текст зі словника",
        }

        await publisher.publish(raw_dict)

        mock_redis.lpush.assert_awaited_once()
        args, _ = mock_redis.lpush.await_args
        queue_key, json_str = args
        assert queue_key == "custom:queue"
        parsed = json.loads(json_str)
        assert parsed["recipient_chat_id"] == 555666777
        assert parsed["title"] == "Зі словника"

    @pytest.mark.asyncio
    async def test_publish_invalid_type_raises_type_error(self) -> None:
        """Перевірка винятку TypeError при спробі опублікувати непідтримуваний тип даних."""
        mock_redis = AsyncMock()
        publisher = RedisQueuePublisher(redis_client=mock_redis)

        with pytest.raises(TypeError, match="Непідтримуваний тип"):
            await publisher.publish(12345)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_publish_many_empty_list(self) -> None:
        """Перевірка поведінки publish_many для порожнього списку (lpush не викликається)."""
        mock_redis = AsyncMock()
        publisher = RedisQueuePublisher(redis_client=mock_redis)

        count = await publisher.publish_many([])
        assert count == 0
        mock_redis.lpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_many_multiple_payloads(self) -> None:
        """Перевірка пакетної відправки списку повідомлень за один виклик lpush."""
        mock_redis = AsyncMock()
        publisher = RedisQueuePublisher(redis_client=mock_redis)

        payload_1 = NotificationPayload(recipient_chat_id=111, title="Т1")
        payload_2 = {
            "recipient_chat_id": 222,
            "title": "Т2",
        }

        count = await publisher.publish_many([payload_1, payload_2])
        assert count == 2

        mock_redis.lpush.assert_awaited_once()
        args, _ = mock_redis.lpush.await_args
        queue_key = args[0]
        json_items = args[1:]
        assert queue_key == "queue:notifications:telegram"
        assert len(json_items) == 2


class TestSqlAlchemyUnitOfWork:
    """Тести для життєвого циклу сесій та транзакцій у SqlAlchemyUnitOfWork."""

    @pytest.mark.asyncio
    async def test_request_scoped_mode(self) -> None:
        """Тест режиму з передачею зовнішньої сесії (Request-Scoped): сесія не закривається в __aexit__."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = SqlAlchemyUnitOfWork(session=mock_session)

        # Поза контекстом звернення до uow.session має викидати RuntimeError
        with pytest.raises(RuntimeError, match="поза контекстом"):
            _ = uow.session

        async with uow:
            assert uow.session is mock_session
            await uow.commit()
            await uow.rollback()

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_awaited_once()
        # Зовнішня сесія НЕ повинна закриватися об'єктом UoW
        mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_scoped_rollback_on_exception(self) -> None:
        """Тест автоматичного відкату транзакції при виникненні винятку всередині контексту."""
        mock_session = AsyncMock(spec=AsyncSession)
        uow = SqlAlchemyUnitOfWork(session=mock_session)

        with pytest.raises(ValueError, match="Критична бізнес-помилка"):
            async with uow:
                raise ValueError("Критична бізнес-помилка")

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_self_contained_mode(self) -> None:
        """Тест режиму зі створенням сесії через factory (Self-Contained): гарантоване закриття."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_factory = MagicMock(return_value=mock_session)
        uow = SqlAlchemyUnitOfWork(session_factory=mock_factory)

        async with uow:
            mock_factory.assert_called_once()
            assert uow.session is mock_session
            await uow.commit()

        mock_session.commit.assert_awaited_once()
        # Внутрішня сесія МАЄ бути закрита при виході з контексту
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_self_contained_rollback_and_close_on_exception(self) -> None:
        """Тест відкату транзакції та гарантованого закриття сесії при помилці в Self-Contained режимі."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_factory = MagicMock(return_value=mock_session)
        uow = SqlAlchemyUnitOfWork(session_factory=mock_factory)

        with pytest.raises(RuntimeError, match="Збій фонової задачі"):
            async with uow:
                raise RuntimeError("Збій фонової задачі")

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()


class TestInspectionHelpers:
    """Тести допоміжних функцій перевірки завантаженості зв'язків (inspection.py)."""

    def test_inspection_on_plain_object(self) -> None:
        """Перевірка поведінки функцій на звичайному об'єкті, який не є моделлю SQLAlchemy."""

        class PlainItem:
            def __init__(self) -> None:
                self.title = "Купити хліб"

        item = PlainItem()

        assert is_loaded(item, "title") is True
        assert is_loaded(item, "non_existing") is False
        assert get_loaded(item, "title") == "Купити хліб"
        assert get_loaded(item, "non_existing", default="дефолт") == "дефолт"

    def test_inspection_with_sqlalchemy_mock_state(self) -> None:
        """Перевірка обробки атрибутів SQLAlchemy інспектора зі значенням NO_VALUE."""
        mock_obj = MagicMock()
        mock_state = MagicMock()

        loaded_attr = MagicMock()
        loaded_attr.loaded_value = ["зв'язок_1", "зв'язок_2"]

        unloaded_attr = MagicMock()
        unloaded_attr.loaded_value = NO_VALUE

        mock_state.attrs = {
            "tags": loaded_attr,
            "reminders": unloaded_attr,
        }

        with patch("src.infrastructure.db.inspection.inspect", return_value=mock_state):
            # Завантажений атрибут
            assert is_loaded(mock_obj, "tags") is True
            assert get_loaded(mock_obj, "tags") == ["зв'язок_1", "зв'язок_2"]

            # Незавантажений атрибут (NO_VALUE)
            assert is_loaded(mock_obj, "reminders") is False
            assert get_loaded(mock_obj, "reminders", default=None) is None
            assert get_loaded(mock_obj, "reminders", default=[]) == []

            # Відсутній атрибут у списку
            assert is_loaded(mock_obj, "other") is False
            assert get_loaded(mock_obj, "other", default="запасне") == "запасне"
