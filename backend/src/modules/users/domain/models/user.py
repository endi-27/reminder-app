from dataclasses import dataclass
from datetime import time

from uuid6 import uuid7

from src.core.domain import AggregateRoot
from src.core.domain.enums import SystemRole
from src.modules.finance.public import ExchangeRateProvider
from src.modules.users.domain.exceptions import (
    SuperAdminDeletionForbiddenError,
    TelegramAccountAlreadyLinkedError,
)
from src.modules.users.domain.models.settings import UserSettings
from src.modules.users.domain.models.telegram_account import UserTelegramAccount


@dataclass(kw_only=True)
class User(AggregateRoot):
    """Корінь агрегата облікового запису користувача системи."""

    username: str
    role: SystemRole = SystemRole.USER
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

    def change_role(self, new_role: SystemRole) -> None:
        """Змінює системну роль користувача."""
        self.ensure_active("змінити роль деактивованого користувача")
        self.role = new_role
        self.mark_updated()

    def soft_delete(self) -> None:
        """М'яке видалення користувача із захистом облікового запису SuperAdmin."""
        if self.role == SystemRole.SUPER_ADMIN:
            raise SuperAdminDeletionForbiddenError("Обліковий запис SuperAdmin не може бути видалений.")
        super().soft_delete()
