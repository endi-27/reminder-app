import calendar
from datetime import UTC, date, datetime, time, timedelta
from typing import ClassVar, cast
from zoneinfo import ZoneInfo

from src.core.exceptions import IncompatibleScheduleLogicError
from src.modules.reminders.domain.enums import (
    EndOfMonthPolicy,
    Priority,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.domain.exceptions import (
    InvalidScheduleConfigError,
)
from src.modules.reminders.domain.value_objects import (
    DailyAtTimesConfig,
    DateWithMonthIntervalConfig,
    ExactDateDeadlineConfig,
    ExactDateTimeDeadlineConfig,
    IntervalDaysConfig,
    IntervalHoursConfig,
    LeadTimes,
    QuietHoursWindow,
    ScheduleConfig,
)


class ScheduleCalculator:
    """
    Доменний сервіс обчислення розкладів, Time-Series проекцій завчасних сповіщень
    та динамічної ескалації пріоритетів.
    """

    ALLOWED_SCHEDULE_LOGICS: ClassVar[dict[ReminderType, frozenset[ScheduleLogicType]]] = {
        ReminderType.ANNIVERSARY: frozenset({ScheduleLogicType.DATE_WITH_MONTH_INTERVAL}),
        ReminderType.OPEN_TASK: frozenset({ScheduleLogicType.DAILY_AT_TIMES}),
        ReminderType.DEADLINE_TASK: frozenset(
            {
                ScheduleLogicType.EXACT_DATETIME_DEADLINE,
                ScheduleLogicType.EXACT_DATE_DEADLINE,
            }
        ),
        ReminderType.SUBSCRIPTION: frozenset(
            {
                ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
                ScheduleLogicType.INTERVAL_DAYS,
            }
        ),
        ReminderType.MEDICATION: frozenset(
            {
                ScheduleLogicType.DAILY_AT_TIMES,
                ScheduleLogicType.INTERVAL_HOURS,
            }
        ),
    }

    @classmethod
    def validate_compatibility(
        cls,
        reminder_type: ReminderType,
        schedule_logic: ScheduleLogicType,
    ) -> None:
        """
        Перевіряє сумісність типу нагадування та обраної логіки планування за матрицею домену.
        У разі невідповідності негайно піднімає IncompatibleScheduleLogicError.
        """
        allowed = cls.ALLOWED_SCHEDULE_LOGICS.get(reminder_type, frozenset())
        if schedule_logic not in allowed:
            allowed_names = ", ".join(logic.value for logic in allowed)
            raise IncompatibleScheduleLogicError(
                f"Логіка планування '{schedule_logic.value}' несумісна з типом нагадування '{reminder_type.value}'. "
                f"Дозволені логіки для цього типу: [{allowed_names}]."
            )

    @staticmethod
    def resolve_calendar_date(
        year: int,
        month: int,
        day: int,
        policy: EndOfMonthPolicy = EndOfMonthPolicy.LAST_DAY_OF_MONTH,
    ) -> date:
        """
        Коригує календарні дати у коротких місяцях (29 лютого у невисокосний рік, 31 число у квітні тощо)
        відповідно до заданої політики EndOfMonthPolicy.
        """
        max_days = calendar.monthrange(year, month)[1]
        if day <= max_days:
            return date(year, month, day)

        if policy == EndOfMonthPolicy.LAST_DAY_OF_MONTH:
            return date(year, month, max_days)

        if policy == EndOfMonthPolicy.FIRST_DAY_OF_NEXT_MONTH:
            if month == 12:
                return date(year + 1, 1, 1)
            return date(year, month + 1, 1)

        return date(year, month, max_days)

    @staticmethod
    def project_lead_time_triggers(
        target_dt_utc: datetime,
        lead_times: LeadTimes,
    ) -> list[datetime]:
        """
        Безстатусна часова проекція (Time-Series Projection):
        Обчислює абсолютні моменти часу T_k = T_target - offset_k для всіх зміщень каскаду
        та повертає впорядкований за зростанням список унікальних точок UTC.
        """
        if target_dt_utc.tzinfo is None:
            target_dt_utc = target_dt_utc.replace(tzinfo=UTC)
        else:
            target_dt_utc = target_dt_utc.astimezone(UTC)

        if not lead_times:
            return [target_dt_utc]

        triggers: set[datetime] = set()
        for offset in lead_times.offsets():
            triggers.add(target_dt_utc - offset)

        return sorted(triggers)

    @staticmethod
    def calculate_dynamic_priority(
        due_datetime_utc: datetime,
        created_at_utc: datetime,
        reference_time_utc: datetime,
        base_priority: Priority | None = None,
        auto_escalate: bool = True,
    ) -> Priority | None:
        """
        Розрахунок динамічного пріоритету задачі з дедлайном за формулою коефіцієнта залишку часу R:
        R = (T_due - T_now) / T_total.

        - Якщо користувач явно вказав base_priority — повертає base_priority.
        - Якщо base_priority is None та auto_escalate == False — повертає None.
        - Якщо до дедлайну <= 24 годин (delta <= 86400) АБО R <= 0.1 -> CRITICAL.
        - Якщо 0.1 < R <= 0.25 -> HIGH.
        - Якщо 0.25 < R <= 0.5 -> MEDIUM.
        - Якщо R > 0.5 -> LOW.
        """
        if base_priority is not None:
            return base_priority

        if not auto_escalate:
            return None

        t_due = due_datetime_utc if due_datetime_utc.tzinfo is not None else due_datetime_utc.replace(tzinfo=UTC)
        t_created = created_at_utc if created_at_utc.tzinfo is not None else created_at_utc.replace(tzinfo=UTC)
        t_now = reference_time_utc if reference_time_utc.tzinfo is not None else reference_time_utc.replace(tzinfo=UTC)

        delta_seconds = (t_due - t_now).total_seconds()
        total_seconds = max((t_due - t_created).total_seconds(), 1.0)
        r = delta_seconds / total_seconds

        if delta_seconds <= 86400 or r <= 0.1:
            return Priority.CRITICAL
        if 0.1 < r <= 0.25:
            return Priority.HIGH
        if 0.25 < r <= 0.5:
            return Priority.MEDIUM
        return Priority.LOW

    @classmethod
    def calculate_next_trigger(
        cls,
        reminder_type: ReminderType,
        schedule_logic: ScheduleLogicType,
        schedule_config: ScheduleConfig,
        reference_time_utc: datetime,
        lead_times: LeadTimes | None = None,
        user_timezone: str = "Europe/Kyiv",
        quiet_hours: QuietHoursWindow | None = None,
        strict_schedule: bool = False,
        is_trial: bool = False,
        trial_end_date: date | None = None,
    ) -> datetime:
        """
        Головний алгоритм детермінованого розрахунку найближчого моменту спрацювання next_trigger_at (UTC).
        Підтримує всі 8 дозволених комбінацій матриці, каскад lead_times, специфіку тріалів
        та вікно тихих годин.
        """
        cls.validate_compatibility(reminder_type, schedule_logic)

        if reference_time_utc.tzinfo is None:
            ref_utc = reference_time_utc.replace(tzinfo=UTC)
        else:
            ref_utc = reference_time_utc.astimezone(UTC)

        user_tz = ZoneInfo(user_timezone)
        ref_local = ref_utc.astimezone(user_tz)

        raw_lead_times = lead_times if lead_times is not None else LeadTimes()

        candidate_dt: datetime | None = None

        # 1. ANNIVERSARY + DATE_WITH_MONTH_INTERVAL
        if reminder_type == ReminderType.ANNIVERSARY:
            cfg1 = cast(DateWithMonthIntervalConfig, schedule_config)
            month = cfg1.month
            if month is None:
                month = cfg1.anchor_date.month if cfg1.anchor_date else ref_local.month

            effective_leads = raw_lead_times if raw_lead_times else LeadTimes(("14d", "7d", "3d", "1d", "0d"))

            # Перебираємо поточний рік та наступні, доки не знайдемо майбутню точку проекції
            for year_offset in range(10):
                target_year = ref_local.year + year_offset
                target_date = cls.resolve_calendar_date(
                    target_year,
                    month,
                    cfg1.day,
                    cfg1.end_of_month_policy,
                )
                target_local = datetime.combine(target_date, cfg1.notify_time, tzinfo=user_tz)
                target_utc = target_local.astimezone(UTC)
                points = cls.project_lead_time_triggers(target_utc, effective_leads)
                future_points = [p for p in points if p > ref_utc]
                if future_points:
                    candidate_dt = min(future_points)
                    break

            if candidate_dt is None:
                raise InvalidScheduleConfigError("Неможливо обчислити наступний час спрацювання для річниці.")

        # 2. OPEN_TASK + DAILY_AT_TIMES або MEDICATION + DAILY_AT_TIMES
        elif schedule_logic == ScheduleLogicType.DAILY_AT_TIMES:
            cfg2 = cast(DailyAtTimesConfig, schedule_config)
            for day_offset in range(7):
                curr_date = ref_local.date() + timedelta(days=day_offset)
                for t in cfg2.times:
                    dt_local = datetime.combine(curr_date, t, tzinfo=user_tz)
                    dt_utc = dt_local.astimezone(UTC)
                    if dt_utc > ref_utc:
                        candidate_dt = dt_utc
                        break
                if candidate_dt is not None:
                    break

            if candidate_dt is None:
                raise InvalidScheduleConfigError("Неможливо обчислити наступний час спрацювання за щоденними годинами.")

        # 3. DEADLINE_TASK
        elif reminder_type == ReminderType.DEADLINE_TASK:
            if schedule_logic == ScheduleLogicType.EXACT_DATETIME_DEADLINE:
                cfg_dt = cast(ExactDateTimeDeadlineConfig, schedule_config)
                target_utc = cfg_dt.due_datetime
            elif schedule_logic == ScheduleLogicType.EXACT_DATE_DEADLINE:
                cfg_d = cast(ExactDateDeadlineConfig, schedule_config)
                target_local = datetime.combine(cfg_d.due_date, cfg_d.default_notify_time, tzinfo=user_tz)
                target_utc = target_local.astimezone(UTC)
            else:
                raise InvalidScheduleConfigError(f"Невідома логіка дедлайну: {schedule_logic}.")

            effective_leads = raw_lead_times if raw_lead_times else LeadTimes(("0d",))
            points = cls.project_lead_time_triggers(target_utc, effective_leads)
            future_points = [p for p in points if p > ref_utc]

            if future_points:
                candidate_dt = min(future_points)
            else:
                # Задача прострочена (T_current >= T_target): щоденне нагадування о 09:00 ранку
                next_morning_local = datetime.combine(ref_local.date(), time(9, 0), tzinfo=user_tz)
                if next_morning_local <= ref_local:
                    next_morning_local = datetime.combine(
                        ref_local.date() + timedelta(days=1),
                        time(9, 0),
                        tzinfo=user_tz,
                    )
                candidate_dt = next_morning_local.astimezone(UTC)

        # 4. SUBSCRIPTION
        elif reminder_type == ReminderType.SUBSCRIPTION:
            # Якщо підписка у тріалі — відлік ведеться від trial_end_date
            if is_trial and trial_end_date is not None:
                trial_target_local = datetime.combine(trial_end_date, time(9, 0), tzinfo=user_tz)
                trial_target_utc = trial_target_local.astimezone(UTC)
                trial_leads = raw_lead_times if raw_lead_times else LeadTimes(("5d", "3d", "1d", "0d"))
                trial_points = cls.project_lead_time_triggers(trial_target_utc, trial_leads)
                future_trial_points = [p for p in trial_points if p > ref_utc]
                if future_trial_points:
                    candidate_dt = min(future_trial_points)

            # Якщо не тріал або всі точки тріалу вичерпані — плануємо за регулярним розкладом
            if candidate_dt is None:
                if schedule_logic == ScheduleLogicType.DATE_WITH_MONTH_INTERVAL:
                    cfg_sub_m = cast(DateWithMonthIntervalConfig, schedule_config)
                    effective_leads = raw_lead_times if raw_lead_times else LeadTimes(("3d", "1d", "0d"))

                    curr_year = ref_local.year
                    curr_month = ref_local.month

                    # Синхронізація з anchor_date для інтервалів більше 1 місяця
                    if cfg_sub_m.interval_months > 1 and cfg_sub_m.anchor_date is not None:
                        anchor_m = cfg_sub_m.anchor_date.year * 12 + (cfg_sub_m.anchor_date.month - 1)
                        current_m = curr_year * 12 + (curr_month - 1)
                        diff_m = current_m - anchor_m
                        if diff_m > 0:
                            steps = diff_m // cfg_sub_m.interval_months
                            aligned_m = anchor_m + steps * cfg_sub_m.interval_months
                            curr_year = aligned_m // 12
                            curr_month = (aligned_m % 12) + 1

                    for _ in range(120):
                        target_date = cls.resolve_calendar_date(
                            curr_year,
                            curr_month,
                            cfg_sub_m.day,
                            cfg_sub_m.end_of_month_policy,
                        )
                        target_local = datetime.combine(target_date, cfg_sub_m.notify_time, tzinfo=user_tz)
                        target_utc = target_local.astimezone(UTC)
                        points = cls.project_lead_time_triggers(target_utc, effective_leads)
                        future_points = [p for p in points if p > ref_utc]
                        if future_points:
                            candidate_dt = min(future_points)
                            break

                        total_m = curr_year * 12 + (curr_month - 1) + cfg_sub_m.interval_months
                        curr_year = total_m // 12
                        curr_month = (total_m % 12) + 1

                    if candidate_dt is None:
                        raise InvalidScheduleConfigError("Неможливо обчислити дату чергового платежу підписки.")

                elif schedule_logic == ScheduleLogicType.INTERVAL_DAYS:
                    cfg_sub_d = cast(IntervalDaysConfig, schedule_config)
                    effective_leads = raw_lead_times if raw_lead_times else LeadTimes(("2d", "1d", "0d"))
                    target_date = cfg_sub_d.anchor_date or ref_local.date()

                    if target_date < ref_local.date():
                        diff_days = (ref_local.date() - target_date).days
                        steps = diff_days // cfg_sub_d.days
                        target_date = target_date + timedelta(days=steps * cfg_sub_d.days)

                    for _ in range(365):
                        target_local = datetime.combine(target_date, cfg_sub_d.notify_time, tzinfo=user_tz)
                        target_utc = target_local.astimezone(UTC)
                        points = cls.project_lead_time_triggers(target_utc, effective_leads)
                        future_points = [p for p in points if p > ref_utc]
                        if future_points:
                            candidate_dt = min(future_points)
                            break
                        target_date = target_date + timedelta(days=cfg_sub_d.days)

                    if candidate_dt is None:
                        raise InvalidScheduleConfigError("Неможливо обчислити наступне спрацювання підписки за днями.")

        # 5. MEDICATION + INTERVAL_HOURS
        elif reminder_type == ReminderType.MEDICATION and schedule_logic == ScheduleLogicType.INTERVAL_HOURS:
            cfg_med_h = cast(IntervalHoursConfig, schedule_config)
            first_today_local = datetime.combine(ref_local.date(), cfg_med_h.first_trigger, tzinfo=user_tz)
            first_today_utc = first_today_local.astimezone(UTC)

            if first_today_utc > ref_utc:
                candidate_dt = first_today_utc
            else:
                diff_seconds = (ref_utc - first_today_utc).total_seconds()
                interval_seconds = cfg_med_h.interval_hours * 3600
                steps = int(diff_seconds // interval_seconds) + 1
                candidate_dt = first_today_utc + timedelta(seconds=steps * interval_seconds)

        if candidate_dt is None:
            msg = (
                f"Не вдалося обчислити наступний час спрацювання для пари "
                f"({reminder_type.value}, {schedule_logic.value})."
            )
            raise InvalidScheduleConfigError(msg)

        # Корекція на вікно тихих годин з урахуванням суворого розкладу
        if quiet_hours is not None:
            candidate_dt = quiet_hours.adjust_trigger_time(candidate_dt, strict_schedule=strict_schedule)

        return candidate_dt
