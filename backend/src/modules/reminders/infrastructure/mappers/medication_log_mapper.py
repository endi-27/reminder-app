from src.infrastructure.db.mappers import BaseMapper
from src.modules.reminders.domain.aggregates import MedicationIntakeLog
from src.modules.reminders.infrastructure.models import MedicationIntakeLogModel


class MedicationIntakeLogMapper(BaseMapper[MedicationIntakeLog, MedicationIntakeLogModel]):
    """Мапер між доменним агрегатом MedicationIntakeLog та ORM-моделлю MedicationIntakeLogModel."""

    def to_domain(self, model: MedicationIntakeLogModel) -> MedicationIntakeLog:
        """Трансформація ORM-моделі MedicationIntakeLogModel у доменний агрегат MedicationIntakeLog."""
        return MedicationIntakeLog(
            id=model.id,
            reminder_id=model.reminder_id,
            scheduled_at=model.scheduled_at,
            recorded_at=model.recorded_at,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
            version=model.version,
        )

    def to_model(self, entity: MedicationIntakeLog) -> MedicationIntakeLogModel:
        """Трансформація чистого доменного агрегата MedicationIntakeLog в ORM-модель."""
        return MedicationIntakeLogModel(
            id=entity.id,
            reminder_id=entity.reminder_id,
            scheduled_at=entity.scheduled_at,
            recorded_at=entity.recorded_at,
            status=entity.status,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
            version=entity.version,
        )
