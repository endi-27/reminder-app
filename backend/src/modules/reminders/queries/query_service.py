from uuid import UUID

from sqlalchemy import func, select

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.infrastructure.db.queries import BaseQueryService
from src.modules.reminders.domain.enums import (
    MedicationLogStatus,
    ReminderStatus,
    ReminderType,
)
from src.modules.reminders.domain.exceptions import ReminderNotFoundError
from src.modules.reminders.infrastructure.models import (
    MedicationIntakeLogModel,
    ReminderModel,
)
from src.modules.reminders.queries.dto import (
    MedicationAdherenceStatsDTO,
    MedicationIntakeLogResponseDTO,
    ReminderResponseDTO,
)


class ReminderQueryService(BaseQueryService):
    """
    Read-side CQRS сервіс для вибірок нагадувань та журналів прийому ліків.

    Виконує виключно операції читання (SELECT) та повертає оптимізовані Pydantic DTO (Інваріант 6).
    """

    async def get_by_id(
        self,
        reminder_id: UUID,
        user_id: UUID | None = None,
    ) -> ReminderResponseDTO | None:
        """Отримує нагадування за його UUID та опціональним user_id."""
        stmt = select(ReminderModel).where(
            ReminderModel.id == reminder_id,
            ReminderModel.deleted_at.is_(None),
        )
        if user_id is not None:
            stmt = stmt.where(ReminderModel.user_id == user_id)

        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return ReminderResponseDTO.model_validate(model)

    async def list_for_user(
        self,
        user_id: UUID,
        params: PaginationParams,
        reminder_type: ReminderType | None = None,
        status: ReminderStatus | None = None,
    ) -> PaginatedResponse[ReminderResponseDTO]:
        """Пагінований список нагадувань користувача з можливістю фільтрації за типом та статусом."""
        base_where = [
            ReminderModel.user_id == user_id,
            ReminderModel.deleted_at.is_(None),
        ]
        if reminder_type is not None:
            base_where.append(ReminderModel.reminder_type == reminder_type)
        if status is not None:
            base_where.append(ReminderModel.status == status)

        count_stmt = select(func.count()).select_from(ReminderModel).where(*base_where)
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        items_stmt = (
            select(ReminderModel)
            .where(*base_where)
            .order_by(ReminderModel.next_trigger_at.asc())
            .offset(params.offset)
            .limit(params.limit)
        )
        items_result = await self._session.execute(items_stmt)
        models = items_result.scalars().all()

        items = [ReminderResponseDTO.model_validate(m) for m in models]
        return PaginatedResponse.create(items=items, total=total, params=params)

    async def get_medication_adherence(
        self,
        reminder_id: UUID,
        user_id: UUID,
    ) -> MedicationAdherenceStatsDTO:
        """Розрахунок статистики комплаєнсу (дотримання лікування) для вказаного нагадування про ліки."""
        reminder = await self.get_by_id(reminder_id, user_id=user_id)
        if reminder is None:
            raise ReminderNotFoundError("Нагадування не знайдено.")

        stmt = (
            select(MedicationIntakeLogModel)
            .where(
                MedicationIntakeLogModel.reminder_id == reminder_id,
                MedicationIntakeLogModel.deleted_at.is_(None),
            )
            .order_by(MedicationIntakeLogModel.scheduled_at.desc())
        )
        result = await self._session.execute(stmt)
        logs = result.scalars().all()

        total_logs = len(logs)
        taken_count = sum(1 for log_item in logs if log_item.status == MedicationLogStatus.TAKEN)
        snoozed_count = sum(1 for log_item in logs if log_item.status == MedicationLogStatus.SNOOZED)
        missed_count = sum(1 for log_item in logs if log_item.status == MedicationLogStatus.MISSED)

        adherence_rate = (taken_count / total_logs * 100.0) if total_logs > 0 else 0.0

        log_dtos = [MedicationIntakeLogResponseDTO.model_validate(log_item) for log_item in logs]
        return MedicationAdherenceStatsDTO(
            reminder_id=reminder_id,
            total_logs=total_logs,
            taken_count=taken_count,
            snoozed_count=snoozed_count,
            missed_count=missed_count,
            adherence_rate_percent=round(adherence_rate, 2),
            logs=log_dtos,
        )
