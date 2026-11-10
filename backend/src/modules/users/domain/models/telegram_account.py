from dataclasses import dataclass
from uuid import UUID

from src.core.domain import BaseEntity


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
