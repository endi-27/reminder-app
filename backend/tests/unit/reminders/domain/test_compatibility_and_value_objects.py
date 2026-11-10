import itertools
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from src.core.exceptions import IncompatibleScheduleLogicError, ValidationException
from src.modules.reminders.domain import (
    CurrencyCode,
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    EndOfMonthPolicy,
    ExactDateTimeDeadlineConfig,
    InvalidLeadTimeFormatError,
    InvalidScheduleConfigError,
    LeadTimes,
    Money,
    QuietHoursWindow,
    ReminderType,
    ScheduleCalculator,
    ScheduleLogicType,
    parse_schedule_config,
    serialize_schedule_config,
)


class TestCompatibilityMatrix:
    """Тестування матриці сумісності 5 типів нагадувань та 6 логік планування."""

    ALLOWED_PAIRS = {
        (ReminderType.ANNIVERSARY, ScheduleLogicType.DATE_WITH_MONTH_INTERVAL),
        (ReminderType.OPEN_TASK, ScheduleLogicType.DAILY_AT_TIMES),
        (ReminderType.DEADLINE_TASK, ScheduleLogicType.EXACT_DATETIME_DEADLINE),
        (ReminderType.DEADLINE_TASK, ScheduleLogicType.EXACT_DATE_DEADLINE),
        (ReminderType.SUBSCRIPTION, ScheduleLogicType.DATE_WITH_MONTH_INTERVAL),
        (ReminderType.SUBSCRIPTION, ScheduleLogicType.INTERVAL_DAYS),
        (ReminderType.MEDICATION, ScheduleLogicType.DAILY_AT_TIMES),
        (ReminderType.MEDICATION, ScheduleLogicType.INTERVAL_HOURS),
    }

    def test_all_eight_allowed_combinations_succeed(self) -> None:
        """Перевіряє, що всі 8 дозволених комбінацій проходять валідацію без помилок."""
        assert len(self.ALLOWED_PAIRS) == 8
        for r_type, s_logic in self.ALLOWED_PAIRS:
            # Не має піднімати виняток
            ScheduleCalculator.validate_compatibility(r_type, s_logic)

    def test_all_incompatible_combinations_raise_error(self) -> None:
        """Перевіряє, що всі решта 22 пари викидають IncompatibleScheduleLogicError."""
        all_possible = set(itertools.product(ReminderType, ScheduleLogicType))
        incompatible_pairs = all_possible - self.ALLOWED_PAIRS
        assert len(incompatible_pairs) == 22

        for r_type, s_logic in incompatible_pairs:
            with pytest.raises(IncompatibleScheduleLogicError) as exc_info:
                ScheduleCalculator.validate_compatibility(r_type, s_logic)
            assert f"'{s_logic.value}' несумісна з типом нагадування '{r_type.value}'" in str(exc_info.value)


class TestMoneyValueObject:
    """Тестування незмінного грошового Value Object."""

    def test_money_creation_and_quantization(self) -> None:
        m1 = Money(Decimal("14.99"))
        assert m1.amount == Decimal("14.99")
        assert m1.currency == CurrencyCode.UAH

        # Перевірка квантування до сотих (ROUND_HALF_UP)
        m2 = Money(Decimal("14.995"), currency=CurrencyCode.USD)
        assert m2.amount == Decimal("15.00")
        assert m2.currency == CurrencyCode.USD

        m3 = Money(Decimal("14.994"), currency=CurrencyCode.EUR)
        assert m3.amount == Decimal("14.99")

    def test_money_str_representation(self) -> None:
        m = Money(Decimal("120.5"), currency=CurrencyCode.USD)
        assert str(m) == "120.50 USD"

    def test_negative_amount_raises_error(self) -> None:
        with pytest.raises(ValidationException, match="Грошова сума не може бути від'ємною"):
            Money(Decimal("-0.01"))


class TestLeadTimesValueObject:
    """Тестування Value Object для каскаду завчасних сповіщень."""

    def test_parse_valid_tokens(self) -> None:
        assert LeadTimes.parse_offset("14d") == timedelta(days=14)
        assert LeadTimes.parse_offset("-7d") == timedelta(days=7)
        assert LeadTimes.parse_offset("+3d") == timedelta(days=3)
        assert LeadTimes.parse_offset("2w") == timedelta(weeks=2)
        assert LeadTimes.parse_offset("5h") == timedelta(hours=5)
        assert LeadTimes.parse_offset("30m") == timedelta(minutes=30)
        assert LeadTimes.parse_offset("0d") == timedelta(0)
        assert LeadTimes.parse_offset("0") == timedelta(0)

    def test_parse_invalid_tokens_raises_error(self) -> None:
        for invalid in ["5xyz", "foo", "d", "14x", "-"]:
            with pytest.raises(InvalidLeadTimeFormatError):
                LeadTimes.parse_offset(invalid)

    def test_lead_times_sorting_and_deduplication(self) -> None:
        # Передаємо у довільному порядку та з дублікатами
        lt = LeadTimes(["1d", "14d", "3d", "14d", "0d", "2h"])
        assert lt.to_list() == ["14d", "3d", "1d", "2h", "0d"]
        assert len(lt) == 5
        assert bool(lt) is True
        assert "14d" in lt
        assert "99d" not in lt

    def test_empty_lead_times(self) -> None:
        lt = LeadTimes()
        assert len(lt) == 0
        assert bool(lt) is False
        assert lt.to_list() == []
        assert lt.offsets() == []


class TestQuietHoursWindow:
    """Тестування вікна тихих годин та винятку strict_schedule."""

    def test_night_quiet_hours_detection_crossing_midnight(self) -> None:
        window = QuietHoursWindow(
            start_time=time(23, 0),
            end_time=time(8, 0),
            timezone_name="Europe/Kyiv",
        )
        # 22:30 за Києвом (20:30 UTC взимку, UTC+2)
        dt_day = datetime(2026, 11, 7, 20, 30, tzinfo=UTC)
        assert window.is_in_quiet_hours(dt_day) is False

        # 23:30 за Києвом (21:30 UTC)
        dt_night_start = datetime(2026, 11, 7, 21, 30, tzinfo=UTC)
        assert window.is_in_quiet_hours(dt_night_start) is True

        # 03:00 за Києвом (01:00 UTC)
        dt_midnight = datetime(2026, 11, 8, 1, 0, tzinfo=UTC)
        assert window.is_in_quiet_hours(dt_midnight) is True

        # 07:59 за Києвом (05:59 UTC)
        dt_morning_quiet = datetime(2026, 11, 8, 5, 59, tzinfo=UTC)
        assert window.is_in_quiet_hours(dt_morning_quiet) is True

        # 08:00 за Києвом (06:00 UTC)
        dt_morning_end = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)
        assert window.is_in_quiet_hours(dt_morning_end) is False

    def test_should_disable_sound_during_quiet_hours(self) -> None:
        window = QuietHoursWindow(
            start_time=time(23, 0),
            end_time=time(8, 0),
            timezone_name="Europe/Kyiv",
        )
        dt_night = datetime(2026, 11, 8, 1, 0, tzinfo=UTC)  # 03:00 Kyiv
        dt_day = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)  # 14:00 Kyiv

        # Вночі без strict_schedule -> звук вимкнено (тихий режим)
        assert window.should_disable_sound(dt_night, strict_schedule=False) is True
        # Вночі зі strict_schedule -> звук увімкнено (обхід тихих годин)
        assert window.should_disable_sound(dt_night, strict_schedule=True) is False
        # Вдень -> звук завжди увімкнено
        assert window.should_disable_sound(dt_day, strict_schedule=False) is False
        assert window.should_disable_sound(dt_day, strict_schedule=True) is False


class TestEndOfMonthAndConfigParsing:
    """Тестування обробки крайових дат місяців та парсингу конфігурацій."""

    def test_end_of_month_resolution(self) -> None:
        # 29 лютого у високосний рік (2028)
        assert ScheduleCalculator.resolve_calendar_date(2028, 2, 29) == date(2028, 2, 29)

        # 29 лютого у невисокосний рік (2027) за LAST_DAY_OF_MONTH -> 28 лютого
        assert ScheduleCalculator.resolve_calendar_date(2027, 2, 29, EndOfMonthPolicy.LAST_DAY_OF_MONTH) == date(
            2027, 2, 28
        )

        # 29 лютого у невисокосний рік (2027) за FIRST_DAY_OF_NEXT_MONTH -> 1 березня
        assert ScheduleCalculator.resolve_calendar_date(2027, 2, 29, EndOfMonthPolicy.FIRST_DAY_OF_NEXT_MONTH) == date(
            2027, 3, 1
        )

        # 31 число у квітні за LAST_DAY_OF_MONTH -> 30 квітня
        assert ScheduleCalculator.resolve_calendar_date(2026, 4, 31, EndOfMonthPolicy.LAST_DAY_OF_MONTH) == date(
            2026, 4, 30
        )

        # 31 число у квітні за FIRST_DAY_OF_NEXT_MONTH -> 1 травня
        assert ScheduleCalculator.resolve_calendar_date(2026, 4, 31, EndOfMonthPolicy.FIRST_DAY_OF_NEXT_MONTH) == date(
            2026, 5, 1
        )

    def test_end_of_month_policy_case_insensitivity(self) -> None:
        assert EndOfMonthPolicy("last_day_of_month") == EndOfMonthPolicy.LAST_DAY_OF_MONTH
        assert EndOfMonthPolicy("first_day_of_next_month") == EndOfMonthPolicy.FIRST_DAY_OF_NEXT_MONTH

    def test_daily_at_times_dedup_and_sort(self) -> None:
        cfg = DailyAtTimesConfig(times=[time(20, 0), time(8, 0), time(8, 0), time(14, 0)])
        assert cfg.times == [time(8, 0), time(14, 0), time(20, 0)]

    def test_parse_and_serialize_configs(self) -> None:
        # Логіка 1
        raw_month = {
            "day": 15,
            "month": 4,
            "interval_months": 12,
            "birth_year": 1990,
            "end_of_month_policy": "last_day_of_month",
        }
        cfg1 = parse_schedule_config(ScheduleLogicType.DATE_WITH_MONTH_INTERVAL, raw_month)
        assert isinstance(cfg1, DateWithMonthIntervalConfig)
        assert cfg1.day == 15
        assert cfg1.birth_year == 1990
        serialized = serialize_schedule_config(cfg1)
        assert serialized["day"] == 15
        assert serialized["end_of_month_policy"] == "LAST_DAY_OF_MONTH"

        # Логіка 3: дедлайн з переведенням у UTC
        raw_dt = {"due_datetime": "2026-11-20T18:00:00Z"}
        cfg3 = parse_schedule_config(ScheduleLogicType.EXACT_DATETIME_DEADLINE, raw_dt)
        assert isinstance(cfg3, ExactDateTimeDeadlineConfig)
        assert cfg3.due_datetime == datetime(2026, 11, 20, 18, 0, tzinfo=UTC)

        # Некоректні дані викликають InvalidScheduleConfigError
        with pytest.raises(InvalidScheduleConfigError):
            parse_schedule_config(ScheduleLogicType.DAILY_AT_TIMES, {"times": []})
