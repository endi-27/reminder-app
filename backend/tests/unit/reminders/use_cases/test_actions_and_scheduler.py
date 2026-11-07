from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from uuid6 import uuid7

from src.core.exceptions import OptimisticLockConflictException
from src.modules.reminders.application.dto import (
    PatchReminderCommand,
    ReminderActionCommand,
    ReminderActionType,
    UpdateReminderCommand,
)
from src.modules.reminders.application.use_cases import (
    HandleReminderActionUseCase,
    PatchReminderUseCase,
    ProcessDueRemindersUseCase,
    UpdateReminderUseCase,
)
from src.modules.reminders.domain.aggregates import (
    MedicationReminder,
    OpenTaskReminder,
    SubscriptionReminder,
)
from src.modules.reminders.domain.enums import (
    CurrencyCode,
    MedicationLogStatus,
    Priority,
    ScheduleLogicType,
)
from src.modules.reminders.domain.value_objects import (
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    IntervalHoursConfig,
    Money,
)
from src.modules.users.domain.enums import ExchangeRateProvider
from src.modules.users.public import UsersPublicGateway
from src.modules.users.queries.dto import UserNotificationContextDTO
from tests.unit.fakes import FakeNotificationPublisher, FakeUnitOfWork
from tests.unit.reminders.fakes import (
    FakeFinanceGateway,
    FakeUsersGateway,
    InMemoryMedicationLogRepository,
    InMemoryReminderRepository,
)


class TestUpdateAndPatchReminderUseCase:
    """Тести оновлення нагадувань (PUT Full Update та PATCH) з перевіркою OCC."""

    @pytest.mark.asyncio
    async def test_update_reminder_full_success(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=111,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        reminder = OpenTaskReminder(
            id=reminder_id,
            user_id=user_id,
            title="Стара назва",
            next_trigger_at=datetime.now(UTC),
            schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
            version=1,
        )
        await repo.save(reminder)

        use_case = UpdateReminderUseCase(uow=uow, reminder_repo=repo, users_gateway=cast(UsersPublicGateway, gateway))
        cmd = UpdateReminderCommand(
            schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
            title="Нова оновлена назва",
            description="Оновлений опис",
            schedule_config={"times": ["10:00:00", "19:00:00"]},
            lead_times=[],
            base_priority=Priority.HIGH,
            version=1,
        )

        updated = await use_case.execute(reminder_id=reminder_id, user_id=user_id, cmd=cmd)
        assert updated.title == "Нова оновлена назва"
        assert updated.description == "Оновлений опис"
        assert uow.committed is True

    @pytest.mark.asyncio
    async def test_update_reminder_occ_conflict_raises_exception(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=111,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        reminder = OpenTaskReminder(
            id=reminder_id,
            user_id=user_id,
            title="Поточна версія 2",
            next_trigger_at=datetime.now(UTC),
            schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
            version=2,
        )
        await repo.save(reminder)

        use_case = UpdateReminderUseCase(uow=uow, reminder_repo=repo, users_gateway=cast(UsersPublicGateway, gateway))
        cmd = UpdateReminderCommand(
            schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
            title="Спроба оновити застарілу версію 1",
            schedule_config={"times": ["10:00:00"]},
            version=1,
        )

        with pytest.raises(OptimisticLockConflictException):
            await use_case.execute(reminder_id=reminder_id, user_id=user_id, cmd=cmd)

    @pytest.mark.asyncio
    async def test_patch_reminder_partial_success(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=111,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        reminder = OpenTaskReminder(
            id=reminder_id,
            user_id=user_id,
            title="Оригінальна справа",
            next_trigger_at=datetime.now(UTC),
            schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
            version=1,
        )
        await repo.save(reminder)

        use_case = PatchReminderUseCase(uow=uow, reminder_repo=repo, users_gateway=cast(UsersPublicGateway, gateway))
        cmd = PatchReminderCommand(
            title="Змінено тільки заголовок",
            version=1,
        )

        patched = await use_case.execute(reminder_id=reminder_id, user_id=user_id, cmd=cmd)
        assert patched.title == "Змінено тільки заголовок"
        assert uow.committed is True


class TestHandleReminderActionUseCase:
    """Тести обробки інтерактивних дій користувача над нагадуванням."""

    @pytest.mark.asyncio
    async def test_subscription_record_payment_decrements_discount(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        med_repo = InMemoryMedicationLogRepository()
        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=111,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        sub = SubscriptionReminder(
            id=reminder_id,
            user_id=user_id,
            title="YouTube Premium Family",
            next_trigger_at=datetime.now(UTC),
            schedule_config=DateWithMonthIntervalConfig(day=10, interval_months=1),
            regular_amount=Money(Decimal("149.00"), CurrencyCode.UAH),
            discount_amount=Money(Decimal("99.00"), CurrencyCode.UAH),
            discount_cycles_total=3,
            discount_cycles_remaining=2,
        )
        await repo.save(sub)

        use_case = HandleReminderActionUseCase(
            uow=uow,
            reminder_repo=repo,
            medication_log_repo=med_repo,
            users_gateway=cast(UsersPublicGateway, gateway),
        )

        cmd = ReminderActionCommand(action=ReminderActionType.RECORD_PAYMENT)
        result = await use_case.execute(reminder_id=reminder_id, user_id=user_id, cmd=cmd)

        assert isinstance(result, SubscriptionReminder)
        assert result.discount_cycles_remaining == 1
        assert uow.committed is True

    @pytest.mark.asyncio
    async def test_medication_record_intake_creates_log(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        med_repo = InMemoryMedicationLogRepository()
        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=111,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        now = datetime.now(UTC)
        med = MedicationReminder(
            id=reminder_id,
            user_id=user_id,
            title="Вітамін D3",
            next_trigger_at=now,
            schedule_config=DailyAtTimesConfig(times=[time(9, 0)]),
            course_duration_days=30,
            medication_start_date=date(2026, 11, 1),
        )
        await repo.save(med)

        use_case = HandleReminderActionUseCase(
            uow=uow,
            reminder_repo=repo,
            medication_log_repo=med_repo,
            users_gateway=cast(UsersPublicGateway, gateway),
        )

        cmd = ReminderActionCommand(
            action=ReminderActionType.RECORD_MEDICATION_INTAKE,
            medication_status=MedicationLogStatus.TAKEN,
        )
        await use_case.execute(reminder_id=reminder_id, user_id=user_id, cmd=cmd)

        logs = await med_repo.list_by_reminder_id(reminder_id)
        assert len(logs) == 1
        assert logs[0].status == MedicationLogStatus.TAKEN
        assert uow.committed is True


class TestProcessDueRemindersUseCase:
    """Тести щохвилинного шедулера ProcessDueRemindersUseCase."""

    @pytest.mark.asyncio
    async def test_night_reminder_deferred_to_morning_during_quiet_hours(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        publisher = FakeNotificationPublisher()
        finance = FakeFinanceGateway()

        # 02:00 за Києвом (00:00 UTC) потрапляє у тихі години (23:00 - 08:00)
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        night_time_kyiv = datetime(2026, 11, 7, 2, 0, tzinfo=kyiv_zone)
        night_utc = night_time_kyiv.astimezone(UTC)

        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=999999,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        reminder = OpenTaskReminder(
            id=reminder_id,
            user_id=user_id,
            title="Нічна задача",
            next_trigger_at=night_utc,
            schedule_config=DailyAtTimesConfig(times=[time(2, 0)]),
        )
        await repo.save(reminder)

        use_case = ProcessDueRemindersUseCase(
            uow=uow,
            reminder_repo=repo,
            users_gateway=cast(UsersPublicGateway, gateway),
            finance_gateway=finance,  # type: ignore[arg-type]
            publisher=publisher,
        )

        result = await use_case.execute(now=night_utc)
        assert result.processed_count == 1
        assert result.deferred_to_quiet_hours == 1
        assert result.notifications_queued == 0
        assert publisher.count() == 0

        # Час перенесено на 08:05 того ж ранку за Києвом
        expected_kyiv = datetime(2026, 11, 7, 8, 5, tzinfo=kyiv_zone)
        expected_utc = expected_kyiv.astimezone(UTC)
        assert reminder.next_trigger_at == expected_utc

    @pytest.mark.asyncio
    async def test_strict_schedule_medication_at_night_not_deferred(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        publisher = FakeNotificationPublisher()
        finance = FakeFinanceGateway()

        kyiv_zone = ZoneInfo("Europe/Kyiv")
        night_time_kyiv = datetime(2026, 11, 7, 2, 0, tzinfo=kyiv_zone)
        night_utc = night_time_kyiv.astimezone(UTC)

        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=999999,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        med = MedicationReminder(
            id=reminder_id,
            user_id=user_id,
            title="Нічний інсулін",
            schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
            next_trigger_at=night_utc,
            schedule_config=IntervalHoursConfig(interval_hours=8),
            strict_schedule=True,
        )
        await repo.save(med)

        use_case = ProcessDueRemindersUseCase(
            uow=uow,
            reminder_repo=repo,
            users_gateway=cast(UsersPublicGateway, gateway),
            finance_gateway=finance,  # type: ignore[arg-type]
            publisher=publisher,
        )

        result = await use_case.execute(now=night_utc)
        assert result.processed_count == 1
        assert result.deferred_to_quiet_hours == 0
        assert result.notifications_queued == 1
        assert publisher.count() == 1
        assert "💊 Час прийому ліків: Нічний інсулін" in publisher.published_payloads[0].body

    @pytest.mark.asyncio
    async def test_usd_subscription_converted_to_uah_with_action_buttons(self) -> None:
        user_id = uuid7()
        reminder_id = uuid7()
        uow = FakeUnitOfWork()
        repo = InMemoryReminderRepository()
        publisher = FakeNotificationPublisher()
        finance = FakeFinanceGateway(rate=Decimal("41.50"), provider="MONOBANK")

        day_time = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)

        gateway = FakeUsersGateway(
            contexts={
                user_id: UserNotificationContextDTO(
                    user_id=user_id,
                    telegram_chat_id=55555,
                    timezone="Europe/Kyiv",
                    quiet_hours_start=time(23, 0),
                    quiet_hours_end=time(8, 0),
                    preferred_bank=ExchangeRateProvider.MONOBANK,
                    auto_deadline_priority_escalation=True,
                )
            }
        )

        sub = SubscriptionReminder(
            id=reminder_id,
            user_id=user_id,
            title="ChatGPT Plus",
            next_trigger_at=day_time,
            schedule_config=DateWithMonthIntervalConfig(day=7, interval_months=1),
            regular_amount=Money(Decimal("20.00"), CurrencyCode.USD),
        )
        await repo.save(sub)

        use_case = ProcessDueRemindersUseCase(
            uow=uow,
            reminder_repo=repo,
            users_gateway=cast(UsersPublicGateway, gateway),
            finance_gateway=finance,  # type: ignore[arg-type]
            publisher=publisher,
        )

        result = await use_case.execute(now=day_time)
        assert result.notifications_queued == 1
        payload = publisher.published_payloads[0]

        assert "20.00 USD (≈ 830.00 грн за курсом MONOBANK)" in payload.body
        button_texts = [b.text for b in payload.buttons]
        assert "💳 Оплачено" in button_texts
        assert "⏰ Нагадати завтра" in button_texts
        assert "❌ Скасувати підписку" in button_texts
