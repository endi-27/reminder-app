import zoneinfo
from dataclasses import dataclass
from datetime import time
from typing import ClassVar
from uuid import UUID

from uuid6 import uuid7

from src.core.domain import AggregateRoot, BaseEntity
from src.modules.users.domain.enums import ExchangeRateProvider, UserRole
from src.modules.users.domain.exceptions import (
    InvalidTimezoneError,
    SuperAdminDeletionForbiddenError,
    TelegramAccountAlreadyLinkedError,
)


@dataclass(kw_only=True)
class UserTelegramAccount(BaseEntity):
    """Доменна сутність прив'язаного профілю Telegram."""

    user_id: UUID
    telegram_id: int
    telegram_chat_id: int
    tg_username: str | None = None
    tg_full_name: str | None = None
    version: int = 1

    def update_profile(
        self,
        *,
        telegram_chat_id: int | None = None,
        tg_username: str | None = None,
        tg_full_name: str | None = None,
    ) -> None:
        """Оновлює реквізити профілю Telegram та фіксує момент оновлення."""
        if telegram_chat_id is not None:
            self.telegram_chat_id = telegram_chat_id
        if tg_username is not None:
            self.tg_username = tg_username
        if tg_full_name is not None:
            self.tg_full_name = tg_full_name
        self.mark_updated()


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


@dataclass(kw_only=True)
class User(AggregateRoot):
    """Корінь агрегата облікового запису користувача системи."""

    username: str
    role: UserRole = UserRole.USER
    password_hash: str | None = None
    telegram_account: UserTelegramAccount | None = None
    settings: UserSettings | None = None

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = UserSettings.create_default(self.id)

    @property
    def current_settings(self) -> UserSettings:
        """Гарантує доступ до налаштувань користувача."""
        if self.settings is None:
            self.settings = UserSettings.create_default(self.id)
        return self.settings

    def link_or_update_telegram(
        self,
        *,
        telegram_id: int,
        telegram_chat_id: int,
        tg_username: str | None = None,
        tg_full_name: str | None = None,
    ) -> UserTelegramAccount:
        """Прив'язує новий профіль Telegram або оновлює реквізити вже підключеного."""
        self.ensure_active("прив'язати Telegram-профіль до деактивованого користувача")

        if self.telegram_account is not None:
            if self.telegram_account.telegram_id != telegram_id:
                raise TelegramAccountAlreadyLinkedError("Цей обліковий запис вже прив'язаний до іншого Telegram ID.")
            self.telegram_account.update_profile(
                telegram_chat_id=telegram_chat_id,
                tg_username=tg_username,
                tg_full_name=tg_full_name,
            )
        else:
            self.telegram_account = UserTelegramAccount(
                id=uuid7(),
                user_id=self.id,
                telegram_id=telegram_id,
                telegram_chat_id=telegram_chat_id,
                tg_username=tg_username,
                tg_full_name=tg_full_name,
                version=1,
            )

        self.mark_updated()
        return self.telegram_account

    def update_settings(
        self,
        *,
        timezone: str | None = None,
        quiet_hours_start: time | None = None,
        quiet_hours_end: time | None = None,
        preferred_bank: ExchangeRateProvider | None = None,
        auto_deadline_priority_escalation: bool | None = None,
    ) -> UserSettings:
        """Оновлює параметри налаштувань користувача."""
        self.ensure_active("змінити налаштування деактивованого користувача")
        settings = self.current_settings
        settings.update(
            timezone=timezone,
            quiet_hours_start=quiet_hours_start,
            quiet_hours_end=quiet_hours_end,
            preferred_bank=preferred_bank,
            auto_deadline_priority_escalation=auto_deadline_priority_escalation,
        )
        self.mark_updated()
        return settings

    def change_password(self, new_password_hash: str) -> None:
        """Змінює пароль облікового запису користувача."""
        self.ensure_active("змінити пароль деактивованого користувача")
        self.password_hash = new_password_hash
        self.mark_updated()

    def change_role(self, new_role: UserRole) -> None:
        """Змінює системну роль користувача."""
        self.ensure_active("змінити роль деактивованого користувача")
        self.role = new_role
        self.mark_updated()

    def soft_delete(self) -> None:
        """М'яке видалення користувача із захистом облікового запису SuperAdmin."""
        if self.role == UserRole.SUPER_ADMIN:
            raise SuperAdminDeletionForbiddenError("Обліковий запис SuperAdmin не може бути видалений.")
        super().soft_delete()
