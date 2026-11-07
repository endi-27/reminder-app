from dataclasses import dataclass
from typing import cast

from src.modules.reminders.domain.aggregates.base import BaseReminder
from src.modules.reminders.domain.enums import EndOfMonthPolicy, ReminderType, ScheduleLogicType
from src.modules.reminders.domain.value_objects import DateWithMonthIntervalConfig


@dataclass(kw_only=True)
class AnniversaryReminder(BaseReminder):
    """
    Доменний агрегат річниці або дня народження.
    Підтримує каскадні завчасні сповіщення та розрахунок віку.
    """

    reminder_type: ReminderType = ReminderType.ANNIVERSARY
    schedule_logic: ScheduleLogicType = ScheduleLogicType.DATE_WITH_MONTH_INTERVAL

    @property
    def config(self) -> DateWithMonthIntervalConfig:
        """Зручний типізований доступ до параметрів конфігурації розкладу."""
        return cast(DateWithMonthIntervalConfig, self.schedule_config)

    @property
    def day(self) -> int:
        """День календарної події."""
        return self.config.day

    @property
    def month(self) -> int | None:
        """Місяць події."""
        return self.config.month

    @property
    def birth_year(self) -> int | None:
        """Рік народження або заснування (якщо відомий)."""
        return self.config.birth_year

    @property
    def end_of_month_policy(self) -> EndOfMonthPolicy:
        """Політика обробки 29 лютого та 31 числа."""
        return self.config.end_of_month_policy

    def calculate_age(self, for_year: int) -> int | None:
        """
        Розраховує вік або кількість років з моменту події для зазначеного календарного року.
        Якщо рік народження не вказано або цільовий рік менший за рік народження — повертає None.
        """
        if self.birth_year is None or for_year < self.birth_year:
            return None
        return for_year - self.birth_year
