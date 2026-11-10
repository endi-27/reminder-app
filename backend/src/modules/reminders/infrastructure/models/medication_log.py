from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.reminders.domain.enums import MedicationLogStatus

if TYPE_CHECKING:
    from src.modules.reminders.infrastructure.models.reminder import ReminderModel


class MedicationIntakeLogModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionedMixin):
    """
    ORM-модель журналу прийому лікарських засобів medication_intake_logs.

    Фіксує історію дотримання курсу лікування для розрахунку комплаєнсу пацієнта.
    """

    __tablename__ = "medication_intake_logs"

    __table_args__ = (
        Index(
            "idx_medication_logs_reminder_scheduled",
            "reminder_id",
            text("scheduled_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    reminder_id: Mapped[UUID] = mapped_column(ForeignKey("reminders.id", ondelete="CASCADE"), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MedicationLogStatus] = mapped_column(
        Enum(
            MedicationLogStatus,
            native_enum=False,
            create_constraint=False,
            length=16,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=MedicationLogStatus.MISSED,
        server_default="MISSED",
        nullable=False,
    )

    reminder: Mapped["ReminderModel"] = relationship(
        "ReminderModel",
        back_populates="intake_logs",
        lazy="raise",
    )
