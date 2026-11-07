from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import pytest
from pydantic import Field
from uuid6 import uuid7

from src.core import (
    AggregateRoot,
    BaseEntity,
    BcryptPasswordHasher,
    CurrentUser,
    InactiveEntityError,
    IncompatibleScheduleLogicError,
    InvalidDiscountCycleError,
    OptimisticLockConflictException,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
    SystemRole,
    create_access_token,
    decode_token,
    mask_sensitive_data,
    settings,
    verify_internal_token,
)
from src.core.events import AsyncEventBus, BaseEvent
from src.utils import (
    check_optimistic_lock,
    deduplicate_preserve_order,
    ensure_utc_datetime,
    normalize_human_name,
    normalize_spaces,
    now_utc,
    unwrap_enum,
    unwrap_enum_or_none,
)
from tests.unit.fakes import (
    FakeEventBus,
    FakeNotificationPublisher,
    FakePasswordHasher,
    FakeUnitOfWork,
)


class DummyEntity(BaseEntity):
    """Тестова конкретна сутність для перевірки BaseEntity."""


class DummyAggregate(AggregateRoot):
    """Тестовий конкретний агрегат для перевірки AggregateRoot."""


class DummyTestEvent(BaseEvent):
    """Тестова доменна подія для перевірки BaseEvent та AsyncEventBus."""

    payload: Annotated[str, Field(description="Тестові корисні дані")]


class DummyDerivedEvent(DummyTestEvent):
    """Похідна тестова подія для перевірки поліморфізму шини подій."""


# ==============================================================================
# Тести BaseEntity та AggregateRoot
# ==============================================================================


def test_base_entity_initialization() -> None:
    entity_id = uuid7()
    entity = DummyEntity(id=entity_id)

    assert entity.id == entity_id
    assert isinstance(entity.created_at, datetime)
    assert entity.created_at.tzinfo == UTC
    assert isinstance(entity.updated_at, datetime)
    assert entity.updated_at.tzinfo == UTC


def test_base_entity_custom_timestamps() -> None:
    entity_id = uuid7()
    custom_created = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    custom_updated = datetime(2025, 1, 2, 12, 0, tzinfo=UTC)
    entity = DummyEntity(id=entity_id, created_at=custom_created, updated_at=custom_updated)

    assert entity.id == entity_id
    assert entity.created_at == custom_created
    assert entity.updated_at == custom_updated


def test_aggregate_root_defaults() -> None:
    agg_id = uuid7()
    agg = DummyAggregate(id=agg_id)

    assert agg.id == agg_id
    assert agg.version == 1
    assert agg.deleted_at is None
    assert isinstance(agg.updated_at, datetime)
    assert agg.updated_at.tzinfo == UTC
    assert agg.is_active is True


def test_aggregate_root_ensure_active_success() -> None:
    agg = DummyAggregate(id=uuid7())
    agg.ensure_active()


def test_aggregate_root_ensure_active_inactive_raises_default() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))
    assert agg.is_active is False

    with pytest.raises(InactiveEntityError) as exc_info:
        agg.ensure_active()

    assert "Неможливо виконати дію над деактивованим ресурсом. Спочатку відновіть його." in str(exc_info.value)


def test_aggregate_root_ensure_active_custom_phrase_and_hint() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))

    with pytest.raises(InactiveEntityError) as exc_info:
        agg.ensure_active(
            action_phrase="змінити стан завдання.",
            restore_hint="Відновіть запис перед змінами.",
        )

    assert "Неможливо змінити стан завдання. Відновіть запис перед змінами." in str(exc_info.value)


def test_aggregate_root_ensure_active_empty_hint() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))

    with pytest.raises(InactiveEntityError) as exc_info:
        agg.ensure_active(
            action_phrase="видалити",
            restore_hint="",
        )

    assert str(exc_info.value) == "Неможливо видалити."


def test_aggregate_root_soft_delete_success() -> None:
    agg = DummyAggregate(id=uuid7())
    assert agg.is_active is True
    assert agg.deleted_at is None

    agg.soft_delete()

    assert agg.is_active is False
    assert agg.deleted_at is not None
    assert agg.updated_at == agg.deleted_at
    assert agg.deleted_at.tzinfo == UTC


def test_aggregate_root_soft_delete_already_inactive_raises() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))
    assert agg.is_active is False

    with pytest.raises(ResourceAlreadyInactiveException) as exc_info:
        agg.soft_delete()

    assert "Цей ресурс вже є неактивним." in str(exc_info.value)


def test_aggregate_root_restore_success() -> None:
    agg = DummyAggregate(id=uuid7(), deleted_at=datetime.now(UTC))
    assert agg.is_active is False

    agg.restore()

    assert agg.is_active is True
    assert agg.deleted_at is None
    assert agg.updated_at is not None
    assert agg.updated_at.tzinfo == UTC


def test_aggregate_root_restore_already_active_raises() -> None:
    agg = DummyAggregate(id=uuid7())
    assert agg.is_active is True

    with pytest.raises(ResourceAlreadyActiveException) as exc_info:
        agg.restore()

    assert "Цей ресурс вже є активним." in str(exc_info.value)


# ==============================================================================
# Тести BaseEvent та AsyncEventBus
# ==============================================================================


def test_base_event_defaults_and_naming() -> None:
    event = DummyTestEvent(payload="test_data")

    assert isinstance(event.event_id, UUID)
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == UTC
    assert event.event_name == "DUMMY_TEST"
    assert event.entity_id is None
    assert event.payload == "test_data"


def test_base_event_name_override() -> None:
    event = DummyTestEvent(payload="override_data", event_name_override="CUSTOM_EVENT_NAME")
    assert event.event_name == "CUSTOM_EVENT_NAME"


@pytest.mark.asyncio
async def test_async_event_bus_subscribe_and_publish() -> None:
    bus = AsyncEventBus()
    received_events: list[DummyTestEvent] = []

    async def sample_handler(event: DummyTestEvent) -> None:
        received_events.append(event)

    bus.subscribe(DummyTestEvent, sample_handler)
    # Перевірка дедуплікації однакового хендлера
    bus.subscribe(DummyTestEvent, sample_handler)

    test_event = DummyTestEvent(payload="message-1")
    await bus.publish(test_event)

    assert len(received_events) == 1
    assert received_events[0] == test_event


@pytest.mark.asyncio
async def test_async_event_bus_decorator_and_polymorphism() -> None:
    bus = AsyncEventBus()
    received_events: list[BaseEvent] = []

    @bus.on(DummyTestEvent)
    async def on_dummy_test(event: DummyTestEvent) -> None:
        received_events.append(event)

    derived_event = DummyDerivedEvent(payload="derived")
    await bus.publish(derived_event)

    assert len(received_events) == 1
    assert received_events[0] == derived_event


@pytest.mark.asyncio
async def test_async_event_bus_safe_execute_handles_exceptions() -> None:
    bus = AsyncEventBus()
    received_events: list[DummyTestEvent] = []

    async def failing_handler(event: DummyTestEvent) -> None:
        raise ValueError("Хендлер впав з помилкою")

    async def working_handler(event: DummyTestEvent) -> None:
        received_events.append(event)

    bus.subscribe(DummyTestEvent, failing_handler)
    bus.subscribe(DummyTestEvent, working_handler)

    test_event = DummyTestEvent(payload="safe-exec")
    # Не має кидати виняток назовні
    await bus.publish(test_event)

    assert len(received_events) == 1
    assert received_events[0] == test_event


def test_async_event_bus_clear() -> None:
    bus = AsyncEventBus()

    async def sample_handler(event: DummyTestEvent) -> None:
        pass

    bus.subscribe(DummyTestEvent, sample_handler)
    assert len(bus._subscribers[DummyTestEvent]) == 1

    bus.clear()
    assert len(bus._subscribers) == 0


# ==============================================================================
# Тести BcryptPasswordHasher
# ==============================================================================


def test_bcrypt_password_hasher_success() -> None:
    hasher = BcryptPasswordHasher(default_rounds=4)
    plain_password = "SuperSecretPassword123!"

    hashed = hasher.hash(plain_password)
    assert hashed.startswith("$2b$")
    assert hasher.verify(plain_password, hashed) is True
    assert hasher.verify("WrongPassword", hashed) is False
    assert hasher.verify(plain_password, "invalid_hash_string") is False


# ==============================================================================
# Тести безпеки, токенів та CurrentUser
# ==============================================================================


def test_create_and_decode_access_token() -> None:
    user_id = uuid7()
    token = create_access_token(
        {"sub": str(user_id), "role": "USER"},
        expires_delta=timedelta(minutes=15),
    )

    decoded = decode_token(token)
    assert decoded["sub"] == str(user_id)
    assert decoded["role"] == "USER"
    assert decoded["type"] == "access"
    assert "exp" in decoded
    assert "iat" in decoded


def test_verify_internal_token() -> None:
    assert verify_internal_token(settings.auth.internal_token) is True
    assert verify_internal_token("invalid-internal-secret-token") is False


def test_current_user_roles_and_properties() -> None:
    user_id = uuid7()

    super_user = CurrentUser(
        id=user_id,
        username="superadmin",
        role=SystemRole.SUPER_ADMIN,
    )
    assert super_user.is_super_admin is True
    assert super_user.is_admin is True

    admin_user = CurrentUser(
        id=user_id,
        username="admin",
        role=SystemRole.ADMIN,
    )
    assert admin_user.is_super_admin is False
    assert admin_user.is_admin is True

    normal_user = CurrentUser(
        id=user_id,
        username="normal_user",
        role=SystemRole.USER,
        telegram_id=123456789,
    )
    assert normal_user.is_super_admin is False
    assert normal_user.is_admin is False
    assert normal_user.telegram_id == 123456789


# ==============================================================================
# Тести маскування даних (mask_sensitive_data)
# ==============================================================================


def test_mask_sensitive_data() -> None:
    payload = {
        "id": 1,
        "username": "ivan_user",
        "password": "secret_password_123",
        "api_key": "my_api_key",
        "nested": {
            "token": "bearer_xyz",
            "safe_field": "hello world",
        },
        "items_list": ["plain_string", {"sub_secret": "hidden_value"}],
        "safe_set": {"item1", "item2"},
    }

    masked = mask_sensitive_data(payload)

    assert masked["username"] == "ivan_user"
    assert masked["password"] == "***MASKED***"
    assert masked["api_key"] == "***MASKED***"
    assert masked["nested"]["token"] == "***MASKED***"
    assert masked["nested"]["safe_field"] == "hello world"
    assert masked["items_list"][0] == "plain_string"
    assert masked["items_list"][1]["sub_secret"] == "***MASKED***"
    assert isinstance(masked["safe_set"], set)


def test_mask_sensitive_data_circular_reference() -> None:
    cyclic_dict: dict[str, object] = {"name": "circular"}
    cyclic_dict["self"] = cyclic_dict

    masked = mask_sensitive_data(cyclic_dict)
    assert masked["name"] == "circular"
    assert masked["self"] == "<circular reference>"


# ==============================================================================
# Тести оптимістичного блокування (check_optimistic_lock)
# ==============================================================================


def test_check_optimistic_lock() -> None:
    # Версії збігаються — виняток не кидається
    check_optimistic_lock(actual_version=2, expected_version=2)

    # Версії відрізняються — кидається OptimisticLockConflictException
    with pytest.raises(OptimisticLockConflictException) as exc_info:
        check_optimistic_lock(actual_version=3, expected_version=2, entity_title="нагадування")

    assert "Дані нагадування було змінено" in str(exc_info.value)
    assert exc_info.value.status_code == 409


# ==============================================================================
# Тести утиліт дат та часу
# ==============================================================================


def test_now_utc() -> None:
    now = now_utc()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_ensure_utc_datetime() -> None:
    # Naive datetime
    naive = datetime(2025, 5, 10, 15, 30)
    aware = ensure_utc_datetime(naive)
    assert aware.tzinfo == UTC
    assert aware.year == 2025
    assert aware.month == 5
    assert aware.day == 10
    assert aware.hour == 15
    assert aware.minute == 30

    # Aware datetime with offset (+2)
    plus2_tz = timezone(timedelta(hours=2))
    aware_plus2 = datetime(2025, 5, 10, 15, 30, tzinfo=plus2_tz)
    converted = ensure_utc_datetime(aware_plus2)
    assert converted.tzinfo == UTC
    assert converted.hour == 13


# ==============================================================================
# Тести санітайзерів та енумів
# ==============================================================================


def test_sanitizers() -> None:
    assert normalize_spaces("  рядок   з   множинними   пробілами  \t\n") == "рядок з множинними пробілами"
    assert normalize_human_name("  шевченко   тарас  григорович  ") == "Шевченко Тарас Григорович"
    assert normalize_human_name("о'коннор д'артаньян жан-поль") == "О'Коннор Д'Артаньян Жан-Поль"

    assert deduplicate_preserve_order([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]
    assert deduplicate_preserve_order(None) is None


def test_enums_unwrap() -> None:
    assert unwrap_enum(SystemRole.ADMIN) == "ADMIN"
    assert unwrap_enum("STRING_VALUE") == "STRING_VALUE"
    assert unwrap_enum_or_none(SystemRole.USER) == "USER"
    assert unwrap_enum_or_none(None) is None


# ==============================================================================
# Тести доменних винятків
# ==============================================================================


def test_domain_exceptions() -> None:
    exc1 = IncompatibleScheduleLogicError()
    assert exc1.status_code == 400
    assert exc1.error_code == "INCOMPATIBLE_SCHEDULE_LOGIC"
    assert "Обрана логіка планування несумісна з цим типом нагадування." in exc1.message

    exc2 = InvalidDiscountCycleError()
    assert exc2.status_code == 400
    assert exc2.error_code == "INVALID_DISCOUNT_CYCLE"
    assert "Некоректні параметри акційного циклу знижки." in exc2.message


# ==============================================================================
# Тести тестових дублерів (Fakes)
# ==============================================================================


@pytest.mark.asyncio
async def test_fake_unit_of_work() -> None:
    uow = FakeUnitOfWork()
    assert uow.committed is False

    async with uow:
        await uow.commit()

    assert uow.committed is True
    assert uow.commit_count == 1
    assert uow.rolled_back is False

    # Симуляція відкату через помилку
    uow_err = FakeUnitOfWork()
    with pytest.raises(RuntimeError):
        async with uow_err:
            raise RuntimeError("Помилка обробки")

    assert uow_err.rolled_back is True


@pytest.mark.asyncio
async def test_fake_event_bus() -> None:
    bus = FakeEventBus()
    event = DummyTestEvent(payload="fake_bus_test")

    await bus.publish(event)
    assert bus.has_event_of_type(DummyTestEvent) is True
    assert bus.get_events_of_type(DummyTestEvent) == [event]


def test_fake_password_hasher() -> None:
    hasher = FakePasswordHasher()
    hashed = hasher.hash("my_secret")
    assert hashed == "hashed_my_secret"
    assert hasher.verify("my_secret", hashed) is True
    assert hasher.verify("wrong_secret", hashed) is False


@pytest.mark.asyncio
async def test_fake_notification_publisher() -> None:
    publisher = FakeNotificationPublisher()
    assert publisher.count() == 0

    payload = {"reminder_id": str(uuid7()), "message": "Час прийняти ліки!"}
    await publisher.publish(payload)

    assert publisher.count() == 1
    assert publisher.published_payloads[0] == payload

    publisher.clear()
    assert publisher.count() == 0
