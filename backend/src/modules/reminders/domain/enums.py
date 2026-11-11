import enum


class ReminderType(enum.StrEnum):
    """Типи нагадувань у системі (Single Table Inheritance дискримінатор)."""

    ANNIVERSARY = "ANNIVERSARY"
    OPEN_TASK = "OPEN_TASK"
    DEADLINE_TASK = "DEADLINE_TASK"
    SUBSCRIPTION = "SUBSCRIPTION"
    MEDICATION = "MEDICATION"


class ScheduleLogicType(enum.StrEnum):
    """Шість канонічних логік планування розкладу нагадувань."""

    DATE_WITH_MONTH_INTERVAL = "DATE_WITH_MONTH_INTERVAL"
    DAILY_AT_TIMES = "DAILY_AT_TIMES"
    EXACT_DATETIME_DEADLINE = "EXACT_DATETIME_DEADLINE"
    EXACT_DATE_DEADLINE = "EXACT_DATE_DEADLINE"
    INTERVAL_DAYS = "INTERVAL_DAYS"
    INTERVAL_HOURS = "INTERVAL_HOURS"


class ReminderStatus(enum.StrEnum):
    """Життєвий цикл та статус активності нагадування."""

    ACTIVE = "ACTIVE"
    TRIAL = "TRIAL"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class Priority(enum.StrEnum):
    """Рівні пріоритету та терміновості нагадування."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EndOfMonthPolicy(enum.StrEnum):
    """Політика обробки крайових дат (29 лютого, 30-31 числа) у коротких місяцях."""

    LAST_DAY_OF_MONTH = "LAST_DAY_OF_MONTH"
    FIRST_DAY_OF_NEXT_MONTH = "FIRST_DAY_OF_NEXT_MONTH"

    @classmethod
    def _missing_(cls, value: object) -> "EndOfMonthPolicy | None":
        """Дозволяє прозоре парсування значень у нижньому регістрі з JSONB."""
        if isinstance(value, str):
            normalized = value.strip().upper()
            for member in cls:
                if member.value == normalized:
                    return member
        return None


class MedicationLogStatus(enum.StrEnum):
    """Статуси відмітки прийому медичного препарату у журналі дотримання."""

    TAKEN = "TAKEN"
    SNOOZED = "SNOOZED"
    MISSED = "MISSED"
