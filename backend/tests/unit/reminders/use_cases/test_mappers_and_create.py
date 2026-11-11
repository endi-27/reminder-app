from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core.domain.enums import CurrencyCode
from src.core.exceptions import IncompatibleScheduleLogicError
from src.modules.finance.public import ExchangeRateProvider
from src.modules.reminders.application.dto import CreateReminderCommand
from src.modules.reminders.application.use_cases import CreateReminderUseCase
from src.modules.reminders.domain.aggregates import (
    AnniversaryReminder,
    DeadlineTaskReminder,
    MedicationIntakeLog,
    MedicationReminder,
    OpenTaskReminder,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.domain.value_objects import (
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    ExactDateTimeDeadlineConfig,
    IntervalHoursConfig,
    LeadTimes,
    Money,
)
from src.modules.reminders.infrastructure.mappers import (
    MedicationIntakeLogMapper,
    ReminderMapper,
)
from src.modules.users.public import UsersPublicGateway
from src.modules.users.queries.dto import UserNotificationContextDTO
from tests.unit.fakes import FakeUnitOfWork
from tests.unit.reminders.fakes import FakeUsersGateway, InMemoryReminderRepository


class TestReminderMapperRoundtrip:
    """Тести двосторонньої трансформації ReminderMapper (to_model -> to_domain) для 5 типів."""

    def test_anniversary_reminder_roundtrip(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        now = datetime.now(UTC)

        entity = AnniversaryReminder(
            id=reminder_id,
            user_id=user_id,
            title="День народження друга",
            description="Купити подарунок",
            next_trigger_at=now,
            schedule_config=DateWithMonthIntervalConfig(
                day=15,
                month=7,
                birth_year=1995,
                notify_time=time(10, 0),
            ),
            lead_times=LeadTimes(["7d", "1d", "0d"]),
        )

        mapper = ReminderMapper()
        model = mapper.to_model(entity)

        assert model.id == reminder_id
        assert model.user_id == user_id
        assert model.reminder_type == ReminderType.ANNIVERSARY
        assert model.title == "День народження друга"
        assert model.schedule_config["day"] == 15
        assert model.lead_times == ["7d", "1d", "0d"]

        restored = mapper.to_domain(model)
        assert isinstance(restored, AnniversaryReminder)
        assert restored.id == entity.id
        assert restored.title == entity.title
        assert restored.birth_year == 1995
        assert restored.calculate_age(2026) == 31
        assert restored.lead_times.to_list() == ["7d", "1d", "0d"]

    def test_open_task_reminder_roundtrip(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        now = datetime.now(UTC)

        entity = OpenTaskReminder(
            id=reminder_id,
            user_id=user_id,
            title="Прочитати статтю",
            next_trigger_at=now,
            schedule_config=DailyAtTimesConfig(times=[time(9, 0), time(18, 0)]),
            base_priority=Priority.MEDIUM,
        )

        mapper = ReminderMapper()
        model = mapper.to_model(entity)
        assert model.base_priority == Priority.MEDIUM

        restored = mapper.to_domain(model)
        assert isinstance(restored, OpenTaskReminder)
        assert restored.base_priority == Priority.MEDIUM
        assert restored.title == "Прочитати статтю"

    def test_deadline_task_reminder_roundtrip(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        now = datetime.now(UTC)
        deadline = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)

        entity = DeadlineTaskReminder(
            id=reminder_id,
            user_id=user_id,
            title="Здати квартальний звіт",
            next_trigger_at=now,
            schedule_config=ExactDateTimeDeadlineConfig(due_datetime=deadline),
            lead_times=LeadTimes(["1d", "2h", "0d"]),
            due_datetime=deadline,
            base_priority=Priority.HIGH,
            calculated_priority=Priority.CRITICAL,
        )

        mapper = ReminderMapper()
        model = mapper.to_model(entity)
        assert model.due_datetime == deadline
        assert model.base_priority == Priority.HIGH
        assert model.calculated_priority == Priority.CRITICAL

        restored = mapper.to_domain(model)
        assert isinstance(restored, DeadlineTaskReminder)
        assert restored.due_datetime == deadline
        assert restored.effective_priority == Priority.HIGH

    def test_subscription_reminder_roundtrip(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        now = datetime.now(UTC)

        entity = SubscriptionReminder(
            id=reminder_id,
            user_id=user_id,
            title="Netflix Premium",
            next_trigger_at=now,
            schedule_config=DateWithMonthIntervalConfig(day=20, interval_months=1),
            regular_amount=Money(Decimal("14.99"), CurrencyCode.USD),
            is_trial=True,
            trial_end_date=date(2026, 11, 25),
            discount_amount=Money(Decimal("9.99"), CurrencyCode.USD),
            discount_cycles_total=3,
            discount_cycles_remaining=2,
        )

        mapper = ReminderMapper()
        model = mapper.to_model(entity)
        assert model.regular_amount == Decimal("14.99")
        assert model.currency == "USD"
        assert model.is_trial is True
        assert model.trial_end_date == date(2026, 11, 25)
        assert model.discount_amount == Decimal("9.99")
        assert model.discount_cycles_total == 3
        assert model.discount_cycles_remaining == 2

        restored = mapper.to_domain(model)
        assert isinstance(restored, SubscriptionReminder)
        assert restored.regular_amount.amount == Decimal("14.99")
        assert restored.regular_amount.currency == CurrencyCode.USD
        assert restored.active_amount.amount == Decimal("9.99")
        assert restored.is_trial is True
        assert restored.discount_cycles_remaining == 2

    def test_medication_reminder_roundtrip(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        now = datetime.now(UTC)

        entity = MedicationReminder(
            id=reminder_id,
            user_id=user_id,
            title="Антибіотик Амоксиклав",
            schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
            next_trigger_at=now,
            schedule_config=IntervalHoursConfig(interval_hours=8),
            course_duration_days=10,
            medication_start_date=date(2026, 11, 1),
            strict_schedule=True,
        )

        mapper = ReminderMapper()
        model = mapper.to_model(entity)
        assert model.course_duration_days == 10
        assert model.medication_start_date == date(2026, 11, 1)
        assert model.medication_end_date == date(2026, 11, 10)
        assert model.strict_schedule is True

        restored = mapper.to_domain(model)
        assert isinstance(restored, MedicationReminder)
        assert restored.strict_schedule is True
        assert restored.course_duration_days == 10
        assert restored.medication_end_date == date(2026, 11, 10)

    def test_medication_intake_log_roundtrip(self) -> None:
        log_id = uuid7()
        reminder_id = uuid7()
        sched_time = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)
        rec_time = datetime(2026, 11, 7, 8, 5, tzinfo=UTC)

        log = MedicationIntakeLog(
            id=log_id,
            reminder_id=reminder_id,
            scheduled_at=sched_time,
            recorded_at=rec_time,
            status=MedicationLogStatus.TAKEN,
        )

        mapper = MedicationIntakeLogMapper()
        model = mapper.to_model(log)
        assert model.id == log_id
        assert model.status == MedicationLogStatus.TAKEN

        restored = mapper.to_domain(model)
        assert restored.id == log_id
        assert restored.status == MedicationLogStatus.TAKEN
        assert restored.recorded_at == rec_time


class TestCreateReminderUseCase:
    """Тести створення нагадувань через CreateReminderUseCase."""

    @pytest.fixture
    def test_context(self) -> tuple[FakeUnitOfWork, InMemoryReminderRepository, FakeUsersGateway, UUID]:
        user_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=12345678,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )
        return uow, repo, gateway, user_id

    @pytest.mark.asyncio
    async def test_create_anniversary_reminder_success(
        self,
        test_context: tuple[FakeUnitOfWork, InMemoryReminderRepository, FakeUsersGateway, UUID],
    ) -> None:
        uow, repo, gateway, user_id = test_context
        use_case = CreateReminderUseCase(
            uow=uow,
            reminder_repo=repo,
            users_gateway=cast(UsersPublicGateway, gateway),
        )

        cmd = CreateReminderCommand(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            title="День народження мами",
            schedule_config={
                "day": 10,
                "month": 5,
                "birth_year": 1965,
                "notify_time": "09:00:00",
            },
            lead_times=["7d", "1d", "0d"],
        )

        reminder = await use_case.execute(user_id=user_id, cmd=cmd)

        assert isinstance(reminder, AnniversaryReminder)
        assert reminder.title == "День народження мами"
        assert reminder.status == ReminderStatus.ACTIVE
        assert uow.committed is True
        assert reminder.id in repo.reminders

    @pytest.mark.asyncio
    async def test_create_deadline_task_with_priority_calculation(
        self,
        test_context: tuple[FakeUnitOfWork, InMemoryReminderRepository, FakeUsersGateway, UUID],
    ) -> None:
        uow, repo, gateway, user_id = test_context
        use_case = CreateReminderUseCase(
            uow=uow,
            reminder_repo=repo,
            users_gateway=cast(UsersPublicGateway, gateway),
        )

        deadline = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
        cmd = CreateReminderCommand(
            reminder_type=ReminderType.DEADLINE_TASK,
            schedule_logic=ScheduleLogicType.EXACT_DATETIME_DEADLINE,
            title="Захист диплому",
            due_datetime=deadline,
            schedule_config={"due_datetime": deadline.isoformat()},
            lead_times=["1d", "2h", "0d"],
        )

        reminder = await use_case.execute(user_id=user_id, cmd=cmd)

        assert isinstance(reminder, DeadlineTaskReminder)
        assert reminder.calculated_priority is not None
        assert uow.committed is True

    @pytest.mark.asyncio
    async def test_create_incompatible_schedule_logic_fails(
        self,
        test_context: tuple[FakeUnitOfWork, InMemoryReminderRepository, FakeUsersGateway, UUID],
    ) -> None:
        uow, repo, gateway, user_id = test_context
        use_case = CreateReminderUseCase(
            uow=uow,
            reminder_repo=repo,
            users_gateway=cast(UsersPublicGateway, gateway),
        )

        cmd = CreateReminderCommand(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
            title="Несумісна річниця",
            schedule_config={"interval_hours": 8},
        )

        with pytest.raises(IncompatibleScheduleLogicError):
            await use_case.execute(user_id=user_id, cmd=cmd)
