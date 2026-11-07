from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError
from uuid6 import uuid7

from src.modules.reminders.domain import (
    AnniversaryReminder,
    CurrencyCode,
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    DeadlineTaskReminder,
    ExactDateTimeDeadlineConfig,
    MedicationReminder,
    Money,
    OpenTaskReminder,
    Priority,
    ReminderStatus,
    ScheduleLogicType,
    SubscriptionReminder,
)
from src.modules.reminders.domain.value_objects import LeadTimes
from src.modules.reminders.infrastructure.models import ReminderModel
from src.modules.reminders.infrastructure.repository import SqlAlchemyReminderRepository
from src.modules.users.domain.enums import UserRole
from src.modules.users.domain.models import User, UserSettings
from src.modules.users.infrastructure.repository import SqlAlchemyUserRepository


async def _create_test_user(session: AsyncSession) -> User:
    """Створює тестового користувача для зв'язування нагадувань через ForeignKey."""
    user_repo = SqlAlchemyUserRepository(session=session)
    user_id = uuid7()
    user = User(
        id=user_id,
        username=f"test_sti_user_{user_id.hex[:6]}",
        role=UserRole.USER,
        password_hash="test_hashed_password",
        settings=UserSettings.create_default(user_id),
    )
    await user_repo.save(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_sti_persistence_and_reconstitution_all_five_types(db_session: AsyncSession) -> None:
    """
    Перевірка збереження та відновлення всіх 5 типів доменних агрегатів
    в єдиній таблиці 'reminders' PostgreSQL 16 (Single Table Inheritance + UUIDv7).
    """
    user = await _create_test_user(db_session)
    repo = SqlAlchemyReminderRepository(session=db_session)
    now = datetime.now(UTC)

    # 1. Створення AnniversaryReminder
    anniversary = AnniversaryReminder(
        id=uuid7(),
        user_id=user.id,
        title="День народження друга",
        schedule_config=DateWithMonthIntervalConfig(
            day=15,
            month=5,
            interval_months=12,
            notify_time=time(10, 0),
            birth_year=1995,
        ),
        lead_times=LeadTimes(["1d", "2h"]),
        next_trigger_at=now + timedelta(days=5),
    )

    # 2. Створення OpenTaskReminder
    open_task = OpenTaskReminder(
        id=uuid7(),
        user_id=user.id,
        title="Переглянути pull request",
        schedule_config=DailyAtTimesConfig(times=[time(9, 0), time(18, 0)]),
        next_trigger_at=now + timedelta(hours=2),
    )

    # 3. Створення DeadlineTaskReminder
    deadline_task = DeadlineTaskReminder(
        id=uuid7(),
        user_id=user.id,
        title="Здати фінансовий звіт",
        schedule_config=ExactDateTimeDeadlineConfig(due_datetime=now + timedelta(days=2)),
        due_datetime=now + timedelta(days=2),
        base_priority=Priority.HIGH,
        lead_times=LeadTimes(["12h", "1h"]),
        next_trigger_at=now + timedelta(hours=12),
    )

    # 4. Створення SubscriptionReminder
    subscription = SubscriptionReminder(
        id=uuid7(),
        user_id=user.id,
        title="Сервіс хостингу серверів",
        schedule_config=DateWithMonthIntervalConfig(day=1, interval_months=1, notify_time=time(12, 0)),
        regular_amount=Money(amount=Decimal("15.99"), currency=CurrencyCode.USD),
        is_trial=True,
        trial_end_date=date.today() + timedelta(days=7),
        discount_cycles_total=3,
        discount_cycles_remaining=2,
        discount_amount=Money(amount=Decimal("9.99"), currency=CurrencyCode.USD),
        next_trigger_at=now + timedelta(days=1),
    )

    # 5. Створення MedicationReminder
    medication = MedicationReminder(
        id=uuid7(),
        user_id=user.id,
        title="Прийом комплексу вітамінів",
        schedule_config=DailyAtTimesConfig(times=[time(8, 30), time(20, 30)]),
        strict_schedule=True,
        course_duration_days=30,
        medication_start_date=date.today(),
        next_trigger_at=now + timedelta(hours=4),
    )

    # Збереження всіх 5 агрегатів у БД
    await repo.save(anniversary)
    await repo.save(open_task)
    await repo.save(deadline_task)
    await repo.save(subscription)
    await repo.save(medication)
    await db_session.flush()

    # Очищуємо кеш сесії для гарантії вибірки з PostgreSQL
    db_session.expunge_all()

    # Перевірка зчитування та поліморфного мапінгу у відповідні класи агрегатів
    saved_anniv = await repo.get_by_id(anniversary.id)
    assert isinstance(saved_anniv, AnniversaryReminder)
    assert saved_anniv.title == "День народження друга"
    assert saved_anniv.birth_year == 1995
    assert saved_anniv.lead_times.to_list() == ["1d", "2h"]

    saved_open = await repo.get_by_id(open_task.id)
    assert isinstance(saved_open, OpenTaskReminder)
    assert saved_open.title == "Переглянути pull request"
    assert isinstance(saved_open.schedule_config, DailyAtTimesConfig)
    assert len(saved_open.schedule_config.times) == 2

    saved_deadline = await repo.get_by_id(deadline_task.id)
    assert isinstance(saved_deadline, DeadlineTaskReminder)
    assert saved_deadline.effective_priority == Priority.HIGH
    assert saved_deadline.lead_times.to_list() == ["12h", "1h"]

    saved_sub = await repo.get_by_id(subscription.id)
    assert isinstance(saved_sub, SubscriptionReminder)
    assert saved_sub.regular_amount.amount == Decimal("15.99")
    assert saved_sub.is_trial is True
    assert saved_sub.discount_cycles_remaining == 2
    assert saved_sub.discount_amount is not None and saved_sub.discount_amount.amount == Decimal("9.99")

    saved_med = await repo.get_by_id(medication.id)
    assert isinstance(saved_med, MedicationReminder)
    assert saved_med.strict_schedule is True
    assert saved_med.course_duration_days == 30


@pytest.mark.asyncio
async def test_fetch_due_for_scheduler_and_skip_locked(db_session: AsyncSession) -> None:
    """
    Перевірка вибірки чергових нагадувань для шедулера ARQ:
    фільтрація status IN ('ACTIVE', 'TRIAL'), next_trigger_at <= now, deleted_at IS NULL.
    """
    user = await _create_test_user(db_session)
    repo = SqlAlchemyReminderRepository(session=db_session)
    now = datetime.now(UTC)

    # Чергове активне нагадування (має вибратися)
    due_reminder = OpenTaskReminder(
        id=uuid7(),
        user_id=user.id,
        title="Термінова задача",
        schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
        next_trigger_at=now - timedelta(minutes=5),
        status=ReminderStatus.ACTIVE,
    )

    # Чергове тріальне нагадування (має вибратися)
    due_trial = SubscriptionReminder(
        id=uuid7(),
        user_id=user.id,
        title="Тріальна підписка",
        schedule_config=DateWithMonthIntervalConfig(day=1, interval_months=1),
        regular_amount=Money(amount=Decimal("10.00"), currency=CurrencyCode.USD),
        is_trial=True,
        trial_end_date=date.today() + timedelta(days=3),
        next_trigger_at=now - timedelta(minutes=1),
        status=ReminderStatus.TRIAL,
    )

    # Нагадування з майбутнім тригером (НЕ має вибратися)
    future_reminder = OpenTaskReminder(
        id=uuid7(),
        user_id=user.id,
        title="Майбутня задача",
        schedule_config=DailyAtTimesConfig(times=[time(14, 0)]),
        next_trigger_at=now + timedelta(hours=3),
        status=ReminderStatus.ACTIVE,
    )

    # Завершене нагадування (НЕ має вибратися)
    completed_reminder = OpenTaskReminder(
        id=uuid7(),
        user_id=user.id,
        title="Виконана задача",
        schedule_config=DailyAtTimesConfig(times=[time(10, 0)]),
        next_trigger_at=now - timedelta(hours=1),
        status=ReminderStatus.COMPLETED,
    )

    # М'яко видалене нагадування (Soft Deleted) (НЕ має вибратися)
    deleted_reminder = OpenTaskReminder(
        id=uuid7(),
        user_id=user.id,
        title="Видалена задача",
        schedule_config=DailyAtTimesConfig(times=[time(11, 0)]),
        next_trigger_at=now - timedelta(minutes=2),
        status=ReminderStatus.ACTIVE,
    )
    deleted_reminder.deleted_at = now - timedelta(minutes=10)

    await repo.save(due_reminder)
    await repo.save(due_trial)
    await repo.save(future_reminder)
    await repo.save(completed_reminder)
    await repo.save(deleted_reminder)
    await db_session.flush()

    due_items = await repo.fetch_due_for_scheduler(now_utc=now, limit=10)
    due_ids = {r.id for r in due_items}

    assert due_reminder.id in due_ids
    assert due_trial.id in due_ids
    assert future_reminder.id not in due_ids
    assert completed_reminder.id not in due_ids
    assert deleted_reminder.id not in due_ids


@pytest.mark.asyncio
async def test_optimistic_locking_occ_version_increment_and_conflict(db_session: AsyncSession) -> None:
    """
    Перевірка оптимістичного блокування OCC:
    - version інкрементується у PostgreSQL при оновленні.
    - Конкурентна зміна рядка в БД викликає помилку StaleDataError при спробі збереження застарілої моделі.
    """
    user = await _create_test_user(db_session)
    now = datetime.now(UTC)

    # Пряме збереження ORM-моделі для тестування OCC
    model = ReminderModel(
        id=uuid7(),
        user_id=user.id,
        reminder_type="OPEN_TASK",
        title="Початкова версія задачі",
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        schedule_config={"times": ["12:00:00"]},
        status=ReminderStatus.ACTIVE,
        next_trigger_at=now + timedelta(hours=1),
        version=1,
    )
    db_session.add(model)
    await db_session.flush()

    assert model.version == 1

    # Успішне оновлення: version стає 2
    model.title = "Оновлена назва задачі"
    await db_session.flush()
    assert model.version == 2

    # Емуляція конкурентної зміни іншим процесом (наприклад, фоновим воркером):
    # Збільшуємо version в базі безпосередньо через SQL
    await db_session.execute(
        text("UPDATE reminders SET version = version + 1 WHERE id = :id"),
        {"id": model.id},
    )

    # Спроба зберегти зміни моделі, яка вважає свою поточну версію = 2 (а в БД вже 3)
    model.title = "Конфліктне паралельне оновлення"
    with pytest.raises(StaleDataError):
        await db_session.flush()
