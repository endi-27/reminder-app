import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.base import NO_VALUE
from uuid6 import uuid7

from src.infrastructure.db.inspection import get_loaded, is_loaded
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.infrastructure.notifications.dto import ActionButton, NotificationPayload
from src.infrastructure.notifications.redis_queue_publisher import RedisQueuePublisher


class TestNotificationDTOs:
    """Тести валідації та серіалізації DTO сповіщень."""

    def test_action_button_valid(self) -> None:
        """Перевірка успішного створення кнопки зі валідними даними."""
        btn = ActionButton(text="Підтвердити", callback_data="confirm_action")
        assert btn.text == "Підтвердити"
        assert btn.callback_data == "confirm_action"

    def test_action_button_validation_errors(self) -> None:
        """Перевірка валідації обмежень довжини тексту та callback_data для кнопки."""
        # Порожній текст кнопки
        with pytest.raises(ValidationError):
            ActionButton(text="", callback_data="action")

        # Перевищення ліміту в 64 символи для тексту
        with pytest.raises(ValidationError):
            ActionButton(text="A" * 65, callback_data="action")

        # Порожній callback_data
        with pytest.raises(ValidationError):
            ActionButton(text="OK", callback_data="")

        # Перевищення ліміту в 64 символи для callback_data
        with pytest.raises(ValidationError):
            ActionButton(text="OK", callback_data="A" * 65)

    def test_notification_payload_valid_and_defaults(self) -> None:
        """Перевірка створення корисного навантаження сповіщення та значень за замовчуванням."""
        reminder_id = uuid7()
        btn = ActionButton(text="Відкласти на 15 хв", callback_data="snooze_15")
        payload = NotificationPayload(
            recipient_chat_id=123456789,
            reminder_id=reminder_id,
            title="Прийом ліків",
            body="Час прийняти Омега-3",
            buttons=[btn],
        )

        assert payload.recipient_channel == "telegram"
        assert payload.recipient_chat_id == 123456789
        assert payload.reminder_id == reminder_id
        assert payload.title == "Прийом ліків"
        assert payload.body == "Час прийняти Омега-3"
        assert len(payload.buttons) == 1
        assert payload.buttons[0].text == "Відкласти на 15 хв"
        assert payload.disable_sound is False

        # Перевірка серіалізації в JSON
        json_data = json.loads(payload.model_dump_json())
        assert json_data["recipient_channel"] == "telegram"
        assert json_data["recipient_chat_id"] == 123456789
        assert json_data["reminder_id"] == str(reminder_id)
        assert json_data["title"] == "Прийом ліків"
        assert len(json_data["buttons"]) == 1

    def test_notification_payload_validation_errors(self) -> None:
        """Перевірка граничних обмежень для заголовка та тексту сповіщення."""
        # Порожній заголовок
        with pytest.raises(ValidationError):
            NotificationPayload(
                recipient_chat_id=123,
                title="",
                body="Тіло сповіщення",
            )

        # Заголовок понад 255 символів
        with pytest.raises(ValidationError):
            NotificationPayload(
                recipient_chat_id=123,
                title="T" * 256,
                body="Тіло сповіщення",
            )

        # Порожній текст
        with pytest.raises(ValidationError):
            NotificationPayload(
                recipient_chat_id=123,
                title="Заголовок",
                body="",
            )


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
            body="Опис події",
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

    @pytest.mark.asyncio
    async def test_publish_dict_payload_success(self) -> None:
        """Перевірка публікації сповіщення, переданого як валідний словник dict."""
        mock_redis = AsyncMock()
        publisher = RedisQueuePublisher(redis_client=mock_redis, queue_key="custom:queue")

        raw_dict = {
            "recipient_chat_id": 555666777,
            "title": "Зі словника",
            "body": "Текст зі словника",
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

        payload_1 = NotificationPayload(recipient_chat_id=111, title="Т1", body="Б1")
        payload_2 = {
            "recipient_chat_id": 222,
            "title": "Т2",
            "body": "Б2",
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
