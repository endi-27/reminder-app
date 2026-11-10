import zoneinfo
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import tzdata

from src.bot.formatters.messages import _format_local_datetime
from src.modules.reminders.domain.enums import ReminderType, ScheduleLogicType
from src.modules.reminders.domain.services.schedule_calculator import ScheduleCalculator
from src.modules.reminders.domain.value_objects import DailyAtTimesConfig, QuietHoursWindow
from src.utils.datetime import configure_tzdata, get_timezone, is_valid_timezone


class TestTzdataConfiguration:
    """Перевірка ізоляції модуля zoneinfo на використання виключно пакета tzdata."""

    def test_tzpath_is_empty_and_uses_tzdata_package(self) -> None:
        configure_tzdata()
        assert zoneinfo.TZPATH == ()
        assert hasattr(tzdata, "__version__")

        # Перевірка завантаження часових поясів з пакета
        kyiv_zone = get_timezone("Europe/Kyiv")
        assert kyiv_zone.key == "Europe/Kyiv"

        warsaw_zone = get_timezone("Europe/Warsaw")
        assert warsaw_zone.key == "Europe/Warsaw"

    def test_is_valid_timezone(self) -> None:
        assert is_valid_timezone("Europe/Kyiv") is True
        assert is_valid_timezone("Europe/Warsaw") is True
        assert is_valid_timezone("America/New_York") is True
        assert is_valid_timezone("UTC") is True

        assert is_valid_timezone("Mars/Colony") is False
        assert is_valid_timezone("") is False
        assert is_valid_timezone("Invalid/Timezone") is False


class TestSpringForwardTransition:
    """
    Тестування весняного переходу на літній час (Spring Forward).

    В Україні та країнах ЄС в останню неділю березня о 03:00 годинники переводять на 04:00 (UTC+2 -> UTC+3).
    У 2026 році перехід відбувається 29 березня 2026 року.
    """

    def test_daily_reminder_retains_local_time_across_spring_forward(self) -> None:
        tz_name = "Europe/Kyiv"
        kyiv_tz = ZoneInfo(tz_name)
        cfg = DailyAtTimesConfig(times=[time(9, 0)])

        # 1. За день до переходу: 28 березня 2026 року (зимовий час UTC+2, 09:00 Київ = 07:00 UTC)
        now_mar28 = datetime(2026, 3, 28, 7, 0, tzinfo=UTC)
        next_mar29 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_mar28,
            user_timezone=tz_name,
        )
        # Наступний день (29 березня) вже є літнім часом (UTC+3), тому 09:00 Київ = 06:00 UTC
        assert next_mar29 == datetime(2026, 3, 29, 6, 0, tzinfo=UTC)
        assert next_mar29.astimezone(kyiv_tz).time() == time(9, 0)

        # 2. У день переходу: 29 березня 2026 року о 06:00 UTC (09:00 Київ)
        now_mar29 = next_mar29
        next_mar30 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_mar29,
            user_timezone=tz_name,
        )
        # 30 березня продовжує діяти літній час: 09:00 Київ = 06:00 UTC
        assert next_mar30 == datetime(2026, 3, 30, 6, 0, tzinfo=UTC)
        assert next_mar30.astimezone(kyiv_tz).time() == time(9, 0)

    def test_spring_forward_gap_hour_handling(self) -> None:
        """
        Тестування крайового випадку, коли нагадування встановлено на 03:30,
        але о 03:00 час переводиться на 04:00 (пропущена година / gap hour).
        """
        tz_name = "Europe/Kyiv"
        kyiv_tz = ZoneInfo(tz_name)
        cfg = DailyAtTimesConfig(times=[time(3, 30)])

        # 28 березня о 03:30 Київ (01:30 UTC)
        now_mar28 = datetime(2026, 3, 28, 1, 30, tzinfo=UTC)
        next_mar29 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_mar28,
            user_timezone=tz_name,
        )
        # Не падає, розраховує безпечний час у день переходу
        assert next_mar29 == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)

        # Перевіряємо, що після переходу наступний день (30 березня) повертається до 03:30
        now_mar29 = next_mar29
        next_mar30 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_mar29,
            user_timezone=tz_name,
        )
        assert next_mar30 == datetime(2026, 3, 30, 0, 30, tzinfo=UTC)
        assert next_mar30.astimezone(kyiv_tz).time() == time(3, 30)


class TestFallBackTransition:
    """
    Тестування осіннього переходу на зимовий час (Fall Back).

    В Україні та країнах ЄС в останню неділю жовтня о 04:00 годинники повертають на 03:00 (UTC+3 -> UTC+2).
    У 2026 році перехід відбувається 25 жовтня 2026 року.
    """

    def test_daily_reminder_retains_local_time_across_fall_back(self) -> None:
        tz_name = "Europe/Kyiv"
        kyiv_tz = ZoneInfo(tz_name)
        cfg = DailyAtTimesConfig(times=[time(9, 0)])

        # 1. За день до переходу: 24 жовтня 2026 року (літній час UTC+3, 09:00 Київ = 06:00 UTC)
        now_oct24 = datetime(2026, 10, 24, 6, 0, tzinfo=UTC)
        next_oct25 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_oct24,
            user_timezone=tz_name,
        )
        # Наступний день (25 жовтня) перейшов на зимовий час (UTC+2), тому 09:00 Київ = 07:00 UTC
        assert next_oct25 == datetime(2026, 10, 25, 7, 0, tzinfo=UTC)
        assert next_oct25.astimezone(kyiv_tz).time() == time(9, 0)

        # 2. У день переходу: 25 жовтня 2026 року о 07:00 UTC (09:00 Київ)
        now_oct25 = next_oct25
        next_oct26 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_oct25,
            user_timezone=tz_name,
        )
        # 26 жовтня діє зимовий час: 09:00 Київ = 07:00 UTC
        assert next_oct26 == datetime(2026, 10, 26, 7, 0, tzinfo=UTC)
        assert next_oct26.astimezone(kyiv_tz).time() == time(9, 0)

    def test_fall_back_ambiguous_hour_no_double_fire(self) -> None:
        """
        Тестування крайового випадку, коли година 03:00-04:00 повторюється двічі.
        Переконуємося, що після першого спрацювання планувальник не надсилає
        повторне сповіщення в ту саму добу, а переносить на наступний день.
        """
        tz_name = "Europe/Kyiv"
        kyiv_tz = ZoneInfo(tz_name)
        cfg = DailyAtTimesConfig(times=[time(3, 30)])

        # 24 жовтня: 03:30 Київ (літній час UTC+3 = 00:30 UTC)
        now_oct24 = datetime(2026, 10, 24, 0, 30, tzinfo=UTC)
        next_oct25 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_oct24,
            user_timezone=tz_name,
        )
        assert next_oct25 == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)

        # Спрацювало 25 жовтня о 00:30 UTC. Наступне спрацювання має перенестися на 26 жовтня!
        now_oct25 = next_oct25
        next_oct26 = ScheduleCalculator.calculate_next_trigger(
            ReminderType.OPEN_TASK,
            ScheduleLogicType.DAILY_AT_TIMES,
            cfg,
            reference_time_utc=now_oct25,
            user_timezone=tz_name,
        )
        assert next_oct26 == datetime(2026, 10, 26, 1, 30, tzinfo=UTC)
        assert next_oct26.astimezone(kyiv_tz).time() == time(3, 30)


class TestQuietHoursAcrossDst:
    """Тестування поведінки вікна тихих годин під час зміни часового поясу."""

    def test_quiet_hours_silent_detection_across_dst(self) -> None:
        qw = QuietHoursWindow(start_time=time(23, 0), end_time=time(8, 0), timezone_name="Europe/Kyiv")

        # 07:30 за Києвом у січні (05:30 UTC) -> у межах тихих годин
        assert qw.should_disable_sound(datetime(2026, 1, 15, 5, 30, tzinfo=UTC)) is True
        # 07:30 за Києвом у липні (04:30 UTC) -> у межах тихих годин
        assert qw.should_disable_sound(datetime(2026, 7, 15, 4, 30, tzinfo=UTC)) is True
        # 08:30 за Києвом у липні (05:30 UTC) -> поза межами тихих годин
        assert qw.should_disable_sound(datetime(2026, 7, 15, 5, 30, tzinfo=UTC)) is False


class TestMessageFormatterAcrossDst:
    """Тестування форматування дат для користувача в боті в різні сезони."""

    def test_message_formatter_formats_correct_local_time_in_winter_and_summer(self) -> None:
        user_tz = "Europe/Kyiv"

        # Зима: 07:00 UTC -> 09:00 Київ
        winter_dt = datetime(2026, 1, 15, 7, 0, tzinfo=UTC)
        winter_str = _format_local_datetime(winter_dt, user_tz)
        assert winter_str == "15.01.2026 09:00"

        # Літо: 06:00 UTC -> 09:00 Київ
        summer_dt = datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
        summer_str = _format_local_datetime(summer_dt, user_tz)
        assert summer_str == "15.07.2026 09:00"
