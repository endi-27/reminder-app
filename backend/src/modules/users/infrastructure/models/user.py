from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.users.domain.enums import UserRole

if TYPE_CHECKING:
    from src.modules.users.infrastructure.models.settings import UserSettingsModel
    from src.modules.users.infrastructure.models.telegram_account import UserTelegramAccountModel


class UserModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionedMixin):
    """ORM-модель таблиці користувачів users."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            native_enum=False,
            create_constraint=False,
            length=16,
            values_callable=lambda obj: [e.value for e in obj],
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
