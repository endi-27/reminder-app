from dataclasses import dataclass
from uuid import UUID

from src.core.domain import BaseEntity


@dataclass(kw_only=True)
class UserTelegramAccount(BaseEntity):
    """Доменна сутність профілю Telegram."""

    user_id: UUID | None = None
    telegram_id: int
    telegram_chat_id: int
    tg_username: str | None = None
    tg_full_name: str | None = None
    version: int = 1

    def update_profile(
        self,
        *,
        telegram_id: int | None = None,
        telegram_chat_id: int | None = None,
        tg_username: str | None = None,
        tg_full_name: str | None = None,
    ) -> None:
        """Оновлює реквізити профілю Telegram та фіксує момент оновлення."""
        if telegram_id is not None:
            self.telegram_id = telegram_id
        if telegram_chat_id is not None:
            self.telegram_chat_id = telegram_chat_id
        if tg_username is not None:
            self.tg_username = tg_username
        if tg_full_name is not None:
            self.tg_full_name = tg_full_name
        self.mark_updated()

    def update_visual_profile(
        self,
        *,
        tg_username: str | None = None,
        tg_full_name: str | None = None,
    ) -> None:
        """Оновлює тільки візуальні реквізити профілю (безпечно для звичайного користувача)."""
        if tg_username is not None:
            self.tg_username = tg_username
        if tg_full_name is not None:
            self.tg_full_name = tg_full_name
        self.mark_updated()

    def link_to_user(self, user_id: UUID) -> None:
        """Прив'язує профіль Telegram до користувача."""
        self.user_id = user_id
        self.mark_updated()

    def unlink(self) -> None:
        """Відв'язує профіль Telegram від користувача."""
        self.user_id = None
        self.mark_updated()
