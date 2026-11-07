from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.modules.reminders.domain import (
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    EndOfMonthPolicy,
    ExactDateTimeDeadlineConfig,
    IntervalDaysConfig,
    IntervalHoursConfig,
    LeadTimes,
    Priority,
    QuietHoursWindow,
    ReminderType,
    ScheduleCalculator,
    ScheduleLogicType,
)


class TestAnniversaryScheduleProjection:
    """Тестування безстатусної часової проекції (Time-Series Projection) для річниць."""

    def test_anniversary_lead_time_cascade_and_next_year_rollover(self) -> None:
        user_tz = ZoneInfo("Europe/Kyiv")
        config = DateWithMonthIntervalConfig(
            day=15,
            month=5,
            interval_months=12,
            notify_time=time(9, 0),
            end_of_month_policy=EndOfMonthPolicy.LAST_DAY_OF_MONTH,
        )
        lead_times = LeadTimes(["14d", "7d", "3d", "1d", "0d"])

        # Цільова дата у 2026 році: 15 травня 09:00 за Києвом (06:00 UTC у літній час)
        target_2026_utc = datetime(2026, 5, 15, 6, 0, tzinfo=UTC)

        # 1. Поточний момент: 1 травня 00:00 UTC (за 14 днів до події)
        ref_1 = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
        next_1 = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_1,
            lead_times=lead_times,
            user_timezone="Europe/Kyiv",
        )
        # Перша точка: за 14 днів, тобто 1 травня 06:00 UTC
        assert next_1 == target_2026_utc - timedelta(days=14)

        # 2. Поточний момент: 1 травня 07:00 UTC (точка "14d" вже минула)
        ref_2 = datetime(2026, 5, 1, 7, 0, tzinfo=UTC)
        next_2 = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_2,
            lead_times=lead_times,
            user_timezone="Europe/Kyiv",
        )
        # Наступна точка: за 7 днів (8 травня 06:00 UTC)
        assert next_2 == target_2026_utc - timedelta(days=7)

        # 3. Динамічне додавання користувачем нової точки "5d" посеред циклу
        updated_leads = LeadTimes(["14d", "7d", "5d", "3d", "1d", "0d"])
        next_dynamic = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_2,
            lead_times=updated_leads,
            user_timezone="Europe/Kyiv",
        )
        # Замість 7d (яка ще попереду 8 травня), перевіряємо, що найближча майбутня — це все ще 7d
        assert next_dynamic == target_2026_utc - timedelta(days=7)

        # Якщо ми вже 9 травня (після 7d), підхоплюється нова точка 5d (10 травня):
        ref_after_7d = datetime(2026, 5, 9, 0, 0, tzinfo=UTC)
        next_5d = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_after_7d,
            lead_times=updated_leads,
            user_timezone="Europe/Kyiv",
        )
        assert next_5d == target_2026_utc - timedelta(days=5)

        # 4. Коли всі точки 2026 року (включно з "0d" 15 травня 06:00 UTC) минули
        ref_after_event = datetime(2026, 5, 16, 0, 0, tzinfo=UTC)
        next_rollover = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_after_event,
            lead_times=lead_times,
            user_timezone="Europe/Kyiv",
        )
        # Автоматичний перехід на 2027 рік: перша точка ("14d" до 15 травня 2027 року)
        target_2027_local = datetime(2027, 5, 15, 9, 0, tzinfo=user_tz)
        target_2027_utc = target_2027_local.astimezone(UTC)
        assert next_rollover == target_2027_utc - timedelta(days=14)

    def test_anniversary_february_29_leap_and_non_leap_years(self) -> None:
        config_last_day = DateWithMonthIntervalConfig(
            day=29,
            month=2,
            interval_months=12,
            notify_time=time(9, 0),
            end_of_month_policy=EndOfMonthPolicy.LAST_DAY_OF_MONTH,
        )
        # У невисокосному 2027 році 29 лютого перетворюється на 28 лютого
        ref_early_2027 = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
        next_2027 = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config_last_day,
            reference_time_utc=ref_early_2027,
            lead_times=LeadTimes(["0d"]),
            user_timezone="Europe/Kyiv",
        )
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        assert next_2027.astimezone(kyiv_zone).date() == date(2027, 2, 28)

        # У високосному 2028 році 29 лютого спрацьовує рівно 29 лютого
        ref_early_2028 = datetime(2028, 1, 1, 0, 0, tzinfo=UTC)
        next_2028 = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.ANNIVERSARY,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config_last_day,
            reference_time_utc=ref_early_2028,
            lead_times=LeadTimes(["0d"]),
            user_timezone="Europe/Kyiv",
        )
        assert next_2028.astimezone(kyiv_zone).date() == date(2028, 2, 29)


class TestSubscriptionScheduleProjection:
    """Тестування планування регулярних підписок та переходів з тріалу."""

    def test_subscription_trial_cascade_and_rollover_to_regular(self) -> None:
        config = DateWithMonthIntervalConfig(
            day=1,
            interval_months=1,
            notify_time=time(9, 0),
        )
        trial_end = date(2026, 11, 20)
        leads = LeadTimes(["5d", "3d", "1d", "0d"])

        # За 4 дні до кінця тріалу (16 листопада): найближча майбутня точка — "3d" (17 листопада)
        ref_trial = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
        next_trial = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.SUBSCRIPTION,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_trial,
            lead_times=leads,
            is_trial=True,
            trial_end_date=trial_end,
            user_timezone="Europe/Kyiv",
        )
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        assert next_trial.astimezone(kyiv_zone).date() == date(2026, 11, 17)

        # Коли тріал закінчився (21 листопада) — планується регулярний платіж на 1 грудня
        ref_post_trial = datetime(2026, 11, 21, 0, 0, tzinfo=UTC)
        next_regular = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.SUBSCRIPTION,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            schedule_config=config,
            reference_time_utc=ref_post_trial,
            lead_times=LeadTimes(["3d", "1d", "0d"]),
            is_trial=False,
            user_timezone="Europe/Kyiv",
        )
        # Для 1 грудня за 3 дні — це 28 листопада
        assert next_regular.astimezone(kyiv_zone).date() == date(2026, 11, 28)

    def test_subscription_interval_days_cycle(self) -> None:
        config = IntervalDaysConfig(
            days=28,
            notify_time=time(9, 0),
            anchor_date=date(2026, 11, 1),
        )
        ref_time = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
        next_dt = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.SUBSCRIPTION,
            schedule_logic=ScheduleLogicType.INTERVAL_DAYS,
            schedule_config=config,
            reference_time_utc=ref_time,
            lead_times=LeadTimes(["2d", "0d"]),
            user_timezone="Europe/Kyiv",
        )
        # Наступний платіж: 1 листопада + 28 днів = 29 листопада. За 2 дні: 27 листопада о 09:00
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        assert next_dt.astimezone(kyiv_zone).date() == date(2026, 11, 27)


class TestMedicationAndTaskSchedules:
    """Тестування щоденних годин, інтервалів та дедлайнів."""

    def test_daily_at_times_multiple_intakes(self) -> None:
        config = DailyAtTimesConfig(times=[time(8, 0), time(14, 0), time(20, 0)])
        # Поточний час: 09:00 за Києвом (07:00 UTC)
        ref_time = datetime(2026, 11, 7, 7, 0, tzinfo=UTC)
        next_dt = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.MEDICATION,
            schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
            schedule_config=config,
            reference_time_utc=ref_time,
            user_timezone="Europe/Kyiv",
        )
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        assert next_dt.astimezone(kyiv_zone) == datetime(2026, 11, 7, 14, 0, tzinfo=kyiv_zone)

    def test_interval_hours_strict_schedule_preserves_night_trigger(self) -> None:
        config = IntervalHoursConfig(interval_hours=8, first_trigger=time(8, 0))
        window = QuietHoursWindow(
            start_time=time(23, 0),
            end_time=time(8, 0),
            timezone_name="Europe/Kyiv",
        )
        # Поточний момент: 18:00 за Києвом (16:00 UTC)
        ref_time = datetime(2026, 11, 7, 16, 0, tzinfo=UTC)

        # 1. За strict_schedule == True нічний прийом о 00:00 (або 02:00) НЕ зсувається
        next_strict = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.MEDICATION,
            schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
            schedule_config=config,
            reference_time_utc=ref_time,
            user_timezone="Europe/Kyiv",
            quiet_hours=window,
            strict_schedule=True,
        )
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        assert next_strict.astimezone(kyiv_zone) == datetime(2026, 11, 8, 0, 0, tzinfo=kyiv_zone)

        # 2. За strict_schedule == False нічний прийом переноситься на 08:05 ранку
        next_non_strict = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.MEDICATION,
            schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
            schedule_config=config,
            reference_time_utc=ref_time,
            user_timezone="Europe/Kyiv",
            quiet_hours=window,
            strict_schedule=False,
        )
        assert next_non_strict.astimezone(kyiv_zone) == datetime(2026, 11, 8, 8, 5, tzinfo=kyiv_zone)

    def test_deadline_task_overdue_morning_fallback(self) -> None:
        due = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
        config = ExactDateTimeDeadlineConfig(due_datetime=due)

        # Задача вже прострочена (поточний момент 7 листопада 14:00 за Києвом)
        ref_overdue = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
        next_dt = ScheduleCalculator.calculate_next_trigger(
            reminder_type=ReminderType.DEADLINE_TASK,
            schedule_logic=ScheduleLogicType.EXACT_DATETIME_DEADLINE,
            schedule_config=config,
            reference_time_utc=ref_overdue,
            lead_times=LeadTimes(["0d"]),
            user_timezone="Europe/Kyiv",
        )
        kyiv_zone = ZoneInfo("Europe/Kyiv")
        # Повертає наступний ранок 8 листопада о 09:00
        assert next_dt.astimezone(kyiv_zone) == datetime(2026, 11, 8, 9, 0, tzinfo=kyiv_zone)


class TestDynamicPriorityCalculation:
    """Тестування формули динамічної ескалації пріоритету R = (T_due - T_now) / T_total."""

    def test_explicit_base_priority_is_respected(self) -> None:
        created = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        due = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
        now = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)  # 4 години до дедлайну

        # Навіть якщо дедлайн близько, явно заданий LOW не змінюється
        prio = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=now,
            base_priority=Priority.LOW,
            auto_escalate=True,
        )
        assert prio == Priority.LOW

    def test_auto_escalate_disabled_returns_none(self) -> None:
        created = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        due = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
        now = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)

        prio = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=now,
            base_priority=None,
            auto_escalate=False,
        )
        assert prio is None

    def test_dynamic_priority_escalation_thresholds(self) -> None:
        created = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        due = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)  # Total 10 днів (240 годин)

        # 1. Залишилося 7 днів (R = 0.7 > 0.5) -> LOW
        prio_low = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=datetime(2026, 11, 4, 0, 0, tzinfo=UTC),
        )
        assert prio_low == Priority.LOW

        # 2. Залишилося 4 дні (R = 0.4: 0.25 < R <= 0.5) -> MEDIUM
        prio_medium = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=datetime(2026, 11, 7, 0, 0, tzinfo=UTC),
        )
        assert prio_medium == Priority.MEDIUM

        # 3. Залишилося 2 дні = 48 годин (R = 0.2: 0.1 < R <= 0.25) -> HIGH
        prio_high = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=datetime(2026, 11, 9, 0, 0, tzinfo=UTC),
        )
        assert prio_high == Priority.HIGH

        # 4. Залишилося 18 годин (delta <= 86400 секунд) -> CRITICAL
        prio_critical_24h = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=datetime(2026, 11, 10, 6, 0, tzinfo=UTC),
        )
        assert prio_critical_24h == Priority.CRITICAL

        # 5. Довга задача (30 днів): залишилося 2 дні (48 год > 24 год, але R = 2/30 = 0.067 <= 0.1) -> CRITICAL
        created_long = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
        due_long = datetime(2026, 10, 31, 0, 0, tzinfo=UTC)
        prio_critical_ratio = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due_long,
            created_at_utc=created_long,
            reference_time_utc=datetime(2026, 10, 29, 0, 0, tzinfo=UTC),
        )
        assert prio_critical_ratio == Priority.CRITICAL

        # 6. Задача прострочена -> CRITICAL
        prio_overdue = ScheduleCalculator.calculate_dynamic_priority(
            due_datetime_utc=due,
            created_at_utc=created,
            reference_time_utc=datetime(2026, 11, 12, 0, 0, tzinfo=UTC),
        )
        assert prio_overdue == Priority.CRITICAL
