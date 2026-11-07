from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.db.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionedMixin,
)
from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)


class ReminderModel(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionedMixin):
    """
    ORM-модель таблиці нагадувань reminders (патерн Single Table Inheritance).

    Зберігає всі 5 типів нагадувань платформи в єдиній таблиці задля оптимізації
    щохвилинної вибірки шедулером через частковий індекс idx_reminders_scheduler.
    """

    __tablename__ = "reminders"

    __table_args__ = (
        Index(
            "idx_reminders_scheduler",
            "next_trigger_at",
            "status",
            postgresql_where=text("status IN ('ACTIVE', 'TRIAL') AND deleted_at IS NULL"),
        ),
        Index(
            "idx_reminders_user_type",
            "user_id",
            "reminder_type",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("regular_amount >= 0", name="regular_amount_non_negative"),
        CheckConstraint("discount_amount >= 0", name="discount_amount_non_negative"),
        CheckConstraint("discount_cycles_total > 0", name="discount_cycles_total_positive"),
        CheckConstraint("discount_cycles_remaining >= 0", name="discount_cycles_remaining_non_negative"),
        CheckConstraint("course_duration_days > 0", name="course_duration_days_positive"),
    )

    # Базові спільні поля
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reminder_type: Mapped[ReminderType] = mapped_column(
        SAEnum(
            ReminderType,
            name="reminder_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        nullable=False,
    )
    schedule_logic: Mapped[ScheduleLogicType] = mapped_column(
        SAEnum(
            ScheduleLogicType,
            name="schedule_logic_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReminderStatus] = mapped_column(
        SAEnum(
            ReminderStatus,
            name="reminder_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        default=ReminderStatus.ACTIVE,
        server_default="ACTIVE",
        nullable=False,
    )
    next_trigger_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schedule_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    lead_times: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )

    # Специфічні поля: Задачі
    due_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    base_priority: Mapped[Priority | None] = mapped_column(
        SAEnum(
            Priority,
            name="priority_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        nullable=True,
    )
    calculated_priority: Mapped[Priority | None] = mapped_column(
        SAEnum(
            Priority,
            name="priority_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        nullable=True,
    )

    # Специфічні поля: Підписки (Фінанси, Тріали, Знижки)
    regular_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), default="UAH", server_default="UAH", nullable=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    trial_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_cycles_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_cycles_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Специфічні поля: Ліки
    course_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    medication_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    medication_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    strict_schedule: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    # Зв'язок із журналом прийому ліків (lazy="raise" за Інваріантом 5)
    intake_logs: Mapped[list["MedicationIntakeLogModel"]] = relationship(
        "MedicationIntakeLogModel",
        back_populates="reminder",
        lazy="raise",
        cascade="all, delete-orphan",
    )


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
        SAEnum(
            MedicationLogStatus,
            name="medication_log_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        default=MedicationLogStatus.MISSED,
        server_default="MISSED",
        nullable=False,
    )

    reminder: Mapped[ReminderModel] = relationship(
        "ReminderModel",
        back_populates="intake_logs",
        lazy="raise",
    )
