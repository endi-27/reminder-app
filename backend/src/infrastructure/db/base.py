from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import DateTime, Integer, MetaData, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from uuid6 import uuid7

POSTGRES_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовий декларативний клас для всіх ORM-моделей SQLAlchemy з єдиною конвенцією найменування."""

    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """
    Міксин первинного ключа UUIDv7 (RFC 9562).

    Часово-впорядкований ідентифікатор гарантує послідовну вставку
    у B-Tree індекси PostgreSQL без фрагментації дискових сторінок.
    """

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid7,
        server_default=text("uuid_generate_v7()"),
    )


class VersionedMixin:
    """Міксин оптимістичного блокування (OCC) за номером версії."""

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


class CreatedAtMixin:
    """
    Міксин часової мітки створення (UTC) для незмінних записів (Append-Only).

    Використовується для таблиць курсів валют, аудит-логів тощо,
    де оновлення рядків не передбачено бізнес-правилами.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    """
    Міксин системних часових міток створення та оновлення (UTC).

    Поєднує server_default=func.now() на рівні схеми PostgreSQL та
    автоматичне оновлення datetime.now(UTC) на рівні Python.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SoftDeleteMixin:
    """Міксин м'якого видалення (UTC часова мітка deleted_at з індексом)."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )


@runtime_checkable
class IdentifiableModelProtocol(Protocol):
    """Протокол для ORM-моделей з первинним ключем UUID (UUIDv7)."""

    id: Mapped[UUID]


@runtime_checkable
class SoftDeleteModelProtocol(IdentifiableModelProtocol, Protocol):
    """Протокол для ORM-моделей з підтримкою м'якого видалення (deleted_at)."""

    deleted_at: Mapped[datetime | None]
