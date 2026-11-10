from datetime import time
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.users.domain.enums import ExchangeRateProvider

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.user import UserModel


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
        Enum(
            ExchangeRateProvider,
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda obj: [e.value for e in obj],
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

    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="settings",
        lazy="raise",
    )
