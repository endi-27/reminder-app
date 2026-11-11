import zoneinfo
from dataclasses import dataclass
from datetime import time
from typing import ClassVar
from uuid import UUID

from uuid6 import uuid7

from src.core.domain import BaseEntity
from src.modules.finance.public import ExchangeRateProvider
from src.modules.users.domain.exceptions import InvalidTimezoneError


@dataclass(kw_only=True)
class UserSettings(BaseEntity):
    """Доменні налаштування користувача (часовий пояс, тихі години, банк)."""

    DEFAULT_TIMEZONE: ClassVar[str] = "Europe/Kyiv"
    DEFAULT_QUIET_START: ClassVar[time] = time(23, 0)
    DEFAULT_QUIET_END: ClassVar[time] = time(8, 0)

    user_id: UUID
    timezone: str = DEFAULT_TIMEZONE
    quiet_hours_start: time = DEFAULT_QUIET_START
    quiet_hours_end: time = DEFAULT_QUIET_END
    preferred_bank: ExchangeRateProvider = ExchangeRateProvider.MONOBANK
    auto_deadline_priority_escalation: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        self._validate_timezone(self.timezone)

    @staticmethod
    def _validate_timezone(timezone_name: str) -> None:
        """Перевіряє коректність ідентифікатора часового поясу IANA."""
        if not timezone_name or not isinstance(timezone_name, str):
            raise InvalidTimezoneError("Часовий пояс не може бути порожнім.")
        try:
            zoneinfo.ZoneInfo(timezone_name)
        except Exception as exc:
            raise InvalidTimezoneError(f"Недійсний ідентифікатор часового поясу: {timezone_name}.") from exc

    def update(
        self,
        *,
        timezone: str | None = None,
        quiet_hours_start: time | None = None,
        quiet_hours_end: time | None = None,
        preferred_bank: ExchangeRateProvider | None = None,
        auto_deadline_priority_escalation: bool | None = None,
    ) -> None:
        """Оновлює користувацькі налаштування з валідацією значень."""
        if timezone is not None:
            self._validate_timezone(timezone)
            self.timezone = timezone
        if quiet_hours_start is not None:
            self.quiet_hours_start = quiet_hours_start
        if quiet_hours_end is not None:
            self.quiet_hours_end = quiet_hours_end
        if preferred_bank is not None:
            self.preferred_bank = preferred_bank
        if auto_deadline_priority_escalation is not None:
            self.auto_deadline_priority_escalation = auto_deadline_priority_escalation
        self.mark_updated()

    def reset_defaults(self) -> None:
        """Скидає параметри налаштувань до системних значень за замовчуванням."""
        self.timezone = self.DEFAULT_TIMEZONE
        self.quiet_hours_start = self.DEFAULT_QUIET_START
        self.quiet_hours_end = self.DEFAULT_QUIET_END
        self.preferred_bank = ExchangeRateProvider.MONOBANK
        self.auto_deadline_priority_escalation = True
        self.mark_updated()

    @classmethod
    def create_default(cls, user_id: UUID) -> "UserSettings":
        """Фабрика створення налаштувань користувача з канонічними значеннями за замовчуванням."""
        return cls(
            id=uuid7(),
            user_id=user_id,
            timezone=cls.DEFAULT_TIMEZONE,
            quiet_hours_start=cls.DEFAULT_QUIET_START,
            quiet_hours_end=cls.DEFAULT_QUIET_END,
            preferred_bank=ExchangeRateProvider.MONOBANK,
            auto_deadline_priority_escalation=True,
            version=1,
        )
