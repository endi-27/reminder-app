from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from uuid6 import uuid7

from src.core.exceptions import (
    InactiveEntityError,
    IncompatibleScheduleLogicError,
    InvalidDiscountCycleError,
    ValidationException,
)
from src.modules.reminders.domain import (
    AnniversaryReminder,
    BaseReminder,
    CurrencyCode,
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    DeadlineTaskReminder,
    EndOfMonthPolicy,
    ExactDateTimeDeadlineConfig,
    IntervalHoursConfig,
    MedicationIntakeLog,
    MedicationLogStatus,
    MedicationReminder,
    Money,
    OpenTaskReminder,
    Priority,
    ReminderStatus,
    ScheduleLogicType,
    SubscriptionReminder,
)
from src.modules.reminders.domain.exceptions import (
    InvalidReminderStateTransitionError,
)


def _assert_status(reminder: BaseReminder, expected: ReminderStatus) -> None:
    assert reminder.status == expected


def _assert_priority(task: DeadlineTaskReminder, expected: Priority | None) -> None:
    assert task.effective_priority == expected


class TestAnniversaryAggregate:
    """Тестування агрегата річниць AnniversaryReminder."""

    def test_anniversary_creation_and_age_calculation(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        cfg = DateWithMonthIntervalConfig(
            day=29,
            month=2,
            interval_months=12,
            birth_year=1996,
            end_of_month_policy=EndOfMonthPolicy.LAST_DAY_OF_MONTH,
        )
        anniversary = AnniversaryReminder(
            id=reminder_id,
            user_id=user_id,
            title="День народження Олександра",
            next_trigger_at=datetime(2027, 2, 14, 7, 0, tzinfo=UTC),
            schedule_config=cfg,
        )

        assert anniversary.day == 29
        assert anniversary.month == 2
        assert anniversary.birth_year == 1996
        assert anniversary.end_of_month_policy == EndOfMonthPolicy.LAST_DAY_OF_MONTH

        # Розрахунок віку: у 2026 виповнюється 30 років
        assert anniversary.calculate_age(2026) == 30
        assert anniversary.calculate_age(2027) == 31
        assert anniversary.calculate_age(1990) is None

    def test_anniversary_incompatible_schedule_logic_fails(self) -> None:
        with pytest.raises(IncompatibleScheduleLogicError):
            AnniversaryReminder(
                id=uuid7(),
                user_id=uuid7(),
                title="Несумісна річниця",
                schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
                schedule_config=IntervalHoursConfig(interval_hours=8),
                next_trigger_at=datetime.now(UTC),
            )


class TestTaskAggregates:
    """Тестування агрегатів OpenTaskReminder та DeadlineTaskReminder."""

    def test_open_task_lifecycle_transitions(self) -> None:
        user_id = uuid7()
        task = OpenTaskReminder(
            id=uuid7(),
            user_id=user_id,
            title="Прочитати статтю про DDD",
            schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
            next_trigger_at=datetime.now(UTC) + timedelta(days=1),
        )

        _assert_status(task, ReminderStatus.ACTIVE)

        # Пауза та відновлення
        task.pause()
        _assert_status(task, ReminderStatus.PAUSED)

        # Спроба повторно призупинити викликає помилку
        task.resume()
        _assert_status(task, ReminderStatus.ACTIVE)

        # Спроба відновити активну задачу
        with pytest.raises(InvalidReminderStateTransitionError):
            task.resume()

        # Відкладення (snooze)
        old_next = task.next_trigger_at
        task.snooze(timedelta(hours=2))
        assert task.next_trigger_at == old_next + timedelta(hours=2)

        # Завершення
        task.complete()
        _assert_status(task, ReminderStatus.COMPLETED)

        # Спроба призупинити завершену задачу
        with pytest.raises(InvalidReminderStateTransitionError):
            task.pause()

    def test_aggregate_root_ensure_active_on_soft_deleted(self) -> None:
        task = OpenTaskReminder(
            id=uuid7(),
            user_id=uuid7(),
            title="Купити каву",
            schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
            next_trigger_at=datetime.now(UTC) + timedelta(days=1),
        )
        task.soft_delete()
        assert task.is_active is False

        with pytest.raises(InactiveEntityError):
            task.pause()

        task.restore()
        assert task.is_active is True
        task.pause()
        assert task.status == ReminderStatus.PAUSED

    def test_deadline_task_priority_recalculation(self) -> None:
        created = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        due = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
        task = DeadlineTaskReminder(
            id=uuid7(),
            user_id=uuid7(),
            title="Здати квартальний звіт",
            due_datetime=due,
            created_at=created,
            next_trigger_at=datetime(2026, 11, 8, 7, 0, tzinfo=UTC),
            schedule_config=ExactDateTimeDeadlineConfig(due_datetime=due),
            base_priority=None,
        )

        # 1. За 7 днів (R = 0.7 > 0.5)
        ref_low = datetime(2026, 11, 4, 0, 0, tzinfo=UTC)
        prio = task.recalculate_priority(ref_low)
        assert prio == Priority.LOW
        _assert_priority(task, Priority.LOW)

        # 2. За 18 годин (< 24 год)
        ref_crit = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
        prio_crit = task.recalculate_priority(ref_crit)
        assert prio_crit == Priority.CRITICAL
        _assert_priority(task, Priority.CRITICAL)

        # 3. Якщо користувач задає явний base_priority — він перекриває динамічний
        task.base_priority = Priority.MEDIUM
        _assert_priority(task, Priority.MEDIUM)


class TestSubscriptionAggregate:
    """Тестування агрегата підписок SubscriptionReminder (тріал, знижки, оплати)."""

    def test_trial_initialization_and_conversion(self) -> None:
        user_id = uuid7()
        cfg = DateWithMonthIntervalConfig(day=1, interval_months=1)

        # Створення тріалу без дати завершення викликає помилку
        with pytest.raises(ValidationException):
            SubscriptionReminder(
                id=uuid7(),
                user_id=user_id,
                title="Apple Music Trial",
                regular_amount=Money(Decimal("4.99"), CurrencyCode.USD),
                is_trial=True,
                trial_end_date=None,
                schedule_config=cfg,
                next_trigger_at=datetime.now(UTC),
            )

        # Коректний тріал отримує статус TRIAL автоматично
        sub = SubscriptionReminder(
            id=uuid7(),
            user_id=user_id,
            title="Apple Music Trial",
            regular_amount=Money(Decimal("4.99"), CurrencyCode.USD),
            is_trial=True,
            trial_end_date=date(2026, 11, 30),
            schedule_config=cfg,
            next_trigger_at=datetime(2026, 11, 25, 7, 0, tzinfo=UTC),
        )
        _assert_status(sub, ReminderStatus.TRIAL)

        # Конвертація у платний
        sub.convert_trial_to_paid(
            reference_time=datetime(2026, 11, 30, 8, 0, tzinfo=UTC),
            user_timezone="Europe/Kyiv",
        )
        assert sub.is_trial is False
        _assert_status(sub, ReminderStatus.ACTIVE)
        assert sub.trial_end_date is None

    def test_promotional_discount_cycles_and_payment_records(self) -> None:
        cfg = DateWithMonthIntervalConfig(day=15, interval_months=1)

        # Валюта знижки має збігатися з регулярною
        with pytest.raises(InvalidDiscountCycleError):
            SubscriptionReminder(
                id=uuid7(),
                user_id=uuid7(),
                title="Spotify Family",
                regular_amount=Money(Decimal("14.99"), CurrencyCode.USD),
                discount_amount=Money(Decimal("99.00"), CurrencyCode.UAH),  # Несумісна валюта
                discount_cycles_total=3,
                discount_cycles_remaining=3,
                schedule_config=cfg,
                next_trigger_at=datetime.now(UTC),
            )

        sub = SubscriptionReminder(
            id=uuid7(),
            user_id=uuid7(),
            title="Spotify Family",
            regular_amount=Money(Decimal("14.99"), CurrencyCode.USD),
            discount_amount=Money(Decimal("1.99"), CurrencyCode.USD),
            discount_cycles_total=3,
            discount_cycles_remaining=3,
            schedule_config=cfg,
            next_trigger_at=datetime(2026, 11, 15, 7, 0, tzinfo=UTC),
        )

        # 1-й платіж: знижка діє (3 -> 2), ціна 1.99
        assert sub.active_amount == Money(Decimal("1.99"), CurrencyCode.USD)
        assert sub.is_last_discount_cycle is False
        paid_1 = sub.record_payment(reference_time=datetime(2026, 11, 15, 8, 0, tzinfo=UTC))
        assert paid_1 == Money(Decimal("1.99"), CurrencyCode.USD)
        assert sub.discount_cycles_remaining == 2

        # 2-й платіж: знижка діє (2 -> 1)
        assert sub.is_last_discount_cycle is False
        paid_2 = sub.record_payment(reference_time=datetime(2026, 12, 15, 8, 0, tzinfo=UTC))
        assert paid_2 == Money(Decimal("1.99"), CurrencyCode.USD)
        assert sub.discount_cycles_remaining == 1
        # Тепер це останній акційний цикл!
        assert sub.is_last_discount_cycle is True

        # 3-й платіж (останній зі знижкою: 1 -> 0)
        paid_3 = sub.record_payment(reference_time=datetime(2027, 1, 15, 8, 0, tzinfo=UTC))
        assert paid_3 == Money(Decimal("1.99"), CurrencyCode.USD)
        assert sub.discount_cycles_remaining == 0
        assert sub.is_last_discount_cycle is False

        # 4-й платіж: знижка вичерпана, автоматично діє регулярна ціна 14.99
        assert sub.active_amount == Money(Decimal("14.99"), CurrencyCode.USD)
        paid_4 = sub.record_payment(reference_time=datetime(2027, 2, 15, 8, 0, tzinfo=UTC))
        assert paid_4 == Money(Decimal("14.99"), CurrencyCode.USD)
        assert sub.discount_cycles_remaining == 0


class TestMedicationAggregate:
    """Тестування агрегата ліків MedicationReminder та логів MedicationIntakeLog."""

    def test_fixed_course_auto_completion(self) -> None:
        user_id = uuid7()
        cfg = DailyAtTimesConfig(times=[time(9, 0)])
        start = date(2026, 11, 1)

        med = MedicationReminder(
            id=uuid7(),
            user_id=user_id,
            title="Антибіотик Амоксиклав 500 мг",
            course_duration_days=3,
            medication_start_date=start,
            next_trigger_at=datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
            schedule_config=cfg,
            strict_schedule=True,
        )

        # 3-денний курс (1, 2, 3 листопада): end_date = 2026-11-03
        assert med.medication_end_date == date(2026, 11, 3)
        assert med.status == ReminderStatus.ACTIVE

        # День 1 (1 листопада): фіксація прийому
        log1 = med.record_intake(
            status=MedicationLogStatus.TAKEN,
            recorded_at=datetime(2026, 11, 1, 7, 5, tzinfo=UTC),
            user_timezone="Europe/Kyiv",
        )
        assert isinstance(log1, MedicationIntakeLog)
        assert log1.status == MedicationLogStatus.TAKEN
        _assert_status(med, ReminderStatus.ACTIVE)

        # День 2 (2 листопада)
        med.record_intake(
            status=MedicationLogStatus.TAKEN,
            recorded_at=datetime(2026, 11, 2, 7, 0, tzinfo=UTC),
            user_timezone="Europe/Kyiv",
        )
        _assert_status(med, ReminderStatus.ACTIVE)

        # День 3 (3 листопада): останній день курсу
        med.record_intake(
            status=MedicationLogStatus.TAKEN,
            recorded_at=datetime(2026, 11, 3, 7, 0, tzinfo=UTC),
            user_timezone="Europe/Kyiv",
        )
        # Оскільки наступна запланована дата 4 листопада > 3 листопада — курс автоматично COMPLETED!
        _assert_status(med, ReminderStatus.COMPLETED)

    def test_indefinite_course_never_completes_automatically(self) -> None:
        cfg = DailyAtTimesConfig(times=[time(8, 0)])
        med = MedicationReminder(
            id=uuid7(),
            user_id=uuid7(),
            title="Вітамін D3 2000 МО",
            course_duration_days=None,  # Безстроковий прийом
            next_trigger_at=datetime(2026, 11, 1, 6, 0, tzinfo=UTC),
            schedule_config=cfg,
        )
        assert med.medication_end_date is None

        med.record_intake(
            status=MedicationLogStatus.TAKEN,
            recorded_at=datetime(2026, 11, 1, 6, 0, tzinfo=UTC),
            user_timezone="Europe/Kyiv",
        )
        assert med.status == ReminderStatus.ACTIVE

    def test_medication_snooze_postpones_by_15_minutes(self) -> None:
        cfg = DailyAtTimesConfig(times=[time(9, 0)])
        med = MedicationReminder(
            id=uuid7(),
            user_id=uuid7(),
            title="Знеболювальне",
            next_trigger_at=datetime(2026, 11, 1, 7, 0, tzinfo=UTC),
            schedule_config=cfg,
        )

        rec_time = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
        log = med.record_intake(status=MedicationLogStatus.SNOOZED, recorded_at=rec_time)
        assert log.status == MedicationLogStatus.SNOOZED
        assert med.next_trigger_at == rec_time + timedelta(minutes=15)
        assert med.status == ReminderStatus.ACTIVE
