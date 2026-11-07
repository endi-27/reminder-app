from datetime import time
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Time
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.users.domain.enums import ExchangeRateProvider, UserRole


class UserModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionedMixin):
    """ORM-модель таблиці користувачів users."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        default=UserRole.USER,
        server_default="USER",
        nullable=False,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Зв'язки 1:1 із забороною неявного I/O (lazy="raise")
    telegram_account: Mapped["UserTelegramAccountModel | None"] = relationship(
        "UserTelegramAccountModel",
        back_populates="user",
        uselist=False,
        lazy="raise",
        cascade="all, delete-orphan",
    )
    settings: Mapped["UserSettingsModel | None"] = relationship(
        "UserSettingsModel",
        back_populates="user",
        uselist=False,
        lazy="raise",
        cascade="all, delete-orphan",
    )


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

    user: Mapped[UserModel] = relationship(
        "UserModel",
        back_populates="telegram_account",
        lazy="raise",
    )


class UserSettingsModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionedMixin):
    """ORM-модель параметрів налаштувань користувача user_settings."""

    __tablename__ = "user_settings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="Europe/Kyiv",
        server_default="Europe/Kyiv",
        nullable=False,
    )
    quiet_hours_start: Mapped[time] = mapped_column(
        Time,
        default=time(23, 0),
        server_default="23:00:00",
        nullable=False,
    )
    quiet_hours_end: Mapped[time] = mapped_column(
        Time,
        default=time(8, 0),
        server_default="08:00:00",
        nullable=False,
    )
    preferred_bank: Mapped[ExchangeRateProvider] = mapped_column(
        SAEnum(
            ExchangeRateProvider,
            name="exchange_rate_provider_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        default=ExchangeRateProvider.MONOBANK,
        server_default="MONOBANK",
        nullable=False,
    )
    auto_deadline_priority_escalation: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    user: Mapped[UserModel] = relationship(
        "UserModel",
        back_populates="settings",
        lazy="raise",
    )
