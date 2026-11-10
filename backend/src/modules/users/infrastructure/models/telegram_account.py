from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.user import UserModel


class UserTelegramAccountModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin):
    """ORM-модель прив'язаного профілю Telegram user_telegram_accounts."""

    __tablename__ = "user_telegram_accounts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    tg_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tg_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="telegram_account",
        lazy="raise",
    )
