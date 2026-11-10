from uuid import UUID

from sqlalchemy import select

from src.infrastructure.db.repositories import SqlAlchemyBaseCrudRepository
from src.modules.reminders.domain.aggregates import MedicationIntakeLog
from src.modules.reminders.domain.interfaces import IMedicationLogRepository
from src.modules.reminders.infrastructure.mappers import MedicationIntakeLogMapper
from src.modules.reminders.infrastructure.models import MedicationIntakeLogModel


class SqlAlchemyMedicationLogRepository(
    SqlAlchemyBaseCrudRepository[MedicationIntakeLog, MedicationIntakeLogModel],
    IMedicationLogRepository,
):
    """Репозиторій для роботи з журналом прийому лікарських засобів medication_intake_logs."""

    _model_cls = MedicationIntakeLogModel
    _mapper = MedicationIntakeLogMapper

    async def list_by_reminder_id(
        self,
        reminder_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> list[MedicationIntakeLog]:
        """Повертає історію прийомів для зазначеного медичного нагадування у хронологічному порядку."""
        stmt = select(MedicationIntakeLogModel).where(MedicationIntakeLogModel.reminder_id == reminder_id)
        if not include_deleted:
            stmt = stmt.where(MedicationIntakeLogModel.deleted_at.is_(None))
        stmt = stmt.order_by(MedicationIntakeLogModel.scheduled_at.desc())
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]
