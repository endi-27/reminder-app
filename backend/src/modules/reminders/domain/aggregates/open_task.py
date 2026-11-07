from dataclasses import dataclass

from src.modules.reminders.domain.aggregates.base import BaseReminder
from src.modules.reminders.domain.enums import Priority, ReminderType, ScheduleLogicType


@dataclass(kw_only=True)
class OpenTaskReminder(BaseReminder):
    """
    Доменний агрегат відкритої справи без чіткого дедлайну (бекстрім).
    Підлягає включенню до ранкових або вечірніх дайджестів завдань.
    """

    reminder_type: ReminderType = ReminderType.OPEN_TASK
    schedule_logic: ScheduleLogicType = ScheduleLogicType.DAILY_AT_TIMES
    base_priority: Priority | None = None
