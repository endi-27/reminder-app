from src.core.exceptions import (
    DomainException,
    NotFoundException,
    ValidationException,
)
from src.core.exceptions import (
    IncompatibleScheduleLogicError as CoreIncompatibleScheduleLogicError,
)
from src.core.exceptions import (
    InvalidDiscountCycleError as CoreInvalidDiscountCycleError,
)


class IncompatibleScheduleLogicError(CoreIncompatibleScheduleLogicError):
    """Виняток несумісності обраної логіки планування з типом нагадування."""


class InvalidDiscountCycleError(CoreInvalidDiscountCycleError):
    """Виняток некоректних параметрів акційного циклу знижки підписки."""


class ReminderNotFoundError(NotFoundException):
    """Виняток, коли нагадування не знайдено в базі даних."""

    default_error_code: str = "REMINDER_NOT_FOUND"
    default_message: str = "Нагадування не знайдено."


class InvalidLeadTimeFormatError(ValidationException):
    """Виняток некоректного формату елемента каскаду завчасного сповіщення."""

    default_error_code: str = "INVALID_LEAD_TIME_FORMAT"
    default_message: str = (
        "Некоректний формат часу завчасного сповіщення. Очікується формат на кшталт '14d', '7d', '2h', '30m' або '0d'."
    )


class InvalidScheduleConfigError(ValidationException):
    """Виняток некоректної конфігурації параметрів розкладу для обраної логіки."""

    default_error_code: str = "INVALID_SCHEDULE_CONFIG"
    default_message: str = "Некоректні параметри конфігурації розкладу нагадування."


class InvalidReminderStateTransitionError(DomainException):
    """Виняток неприпустимого переходу між статусами життєвого циклу нагадування."""

    default_error_code: str = "INVALID_REMINDER_STATE_TRANSITION"
    default_message: str = "Неприпустима зміна статусу нагадування для поточного стану."


class MedicationLogNotFoundError(NotFoundException):
    """Виняток, коли запис журналу прийому медикаментів не знайдено."""

    default_error_code: str = "MEDICATION_LOG_NOT_FOUND"
    default_message: str = "Запис журналу прийому ліків не знайдено."
