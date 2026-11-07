from src.modules.reminders.domain.aggregates.anniversary import AnniversaryReminder
from src.modules.reminders.domain.aggregates.base import BaseReminder
from src.modules.reminders.domain.aggregates.deadline_task import DeadlineTaskReminder
from src.modules.reminders.domain.aggregates.medication import (
    MedicationIntakeLog,
    MedicationReminder,
)
from src.modules.reminders.domain.aggregates.open_task import OpenTaskReminder
from src.modules.reminders.domain.aggregates.subscription import SubscriptionReminder

type ReminderAggregate = (
    AnniversaryReminder | OpenTaskReminder | DeadlineTaskReminder | SubscriptionReminder | MedicationReminder
)

__all__ = [
    "AnniversaryReminder",
    "BaseReminder",
    "DeadlineTaskReminder",
    "MedicationIntakeLog",
    "MedicationReminder",
    "OpenTaskReminder",
    "ReminderAggregate",
    "SubscriptionReminder",
]
