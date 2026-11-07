from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_uow
from src.core.database import get_db_session
from src.core.protocols import INotificationPublisher, IUnitOfWork
from src.core.redis import RedisClient, get_redis_client
from src.infrastructure.notifications.redis_queue_publisher import RedisQueuePublisher
from src.modules.finance.public import FinancePublicGateway
from src.modules.reminders.application.use_cases import (
    CreateReminderUseCase,
    HandleReminderActionUseCase,
    HardDeleteReminderUseCase,
    PatchReminderUseCase,
    SoftDeleteReminderUseCase,
    UpdateReminderUseCase,
)
from src.modules.reminders.domain.interfaces import (
    IMedicationLogRepository,
    IReminderRepository,
)
from src.modules.reminders.infrastructure.repository import (
    SqlAlchemyMedicationLogRepository,
    SqlAlchemyReminderRepository,
)
from src.modules.reminders.queries.query_service import ReminderQueryService
from src.modules.users.public import UsersPublicGateway


def get_reminder_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IReminderRepository:
    """Фабрика створення репозиторію нагадувань."""
    return SqlAlchemyReminderRepository(session)


def get_medication_log_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IMedicationLogRepository:
    """Фабрика створення репозиторію журналу прийому ліків."""
    return SqlAlchemyMedicationLogRepository(session)


def get_reminder_query_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReminderQueryService:
    """Фабрика створення CQRS Read-Side сервісу вибірок нагадувань."""
    return ReminderQueryService(session)


def get_users_public_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
) -> UsersPublicGateway:
    """Фабрика публічного фасаду модуля користувачів."""
    return UsersPublicGateway(session=session, uow=uow)


def get_finance_public_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
) -> FinancePublicGateway:
    """Фабрика публічного фасаду модуля фінансів."""
    return FinancePublicGateway(session=session, uow=uow)


def get_notification_publisher(
    redis_client: Annotated[RedisClient, Depends(get_redis_client)],
) -> INotificationPublisher:
    """Фабрика видавця сповіщень у Redis-чергу."""
    return RedisQueuePublisher(redis_client=redis_client)


def get_create_reminder_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    reminder_repo: Annotated[IReminderRepository, Depends(get_reminder_repository)],
    users_gateway: Annotated[UsersPublicGateway, Depends(get_users_public_gateway)],
) -> CreateReminderUseCase:
    """Фабрика Use Case створення нагадування."""
    return CreateReminderUseCase(
        uow=uow,
        reminder_repo=reminder_repo,
        users_gateway=users_gateway,
    )


def get_update_reminder_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    reminder_repo: Annotated[IReminderRepository, Depends(get_reminder_repository)],
    users_gateway: Annotated[UsersPublicGateway, Depends(get_users_public_gateway)],
) -> UpdateReminderUseCase:
    """Фабрика Use Case повного оновлення нагадування (PUT)."""
    return UpdateReminderUseCase(
        uow=uow,
        reminder_repo=reminder_repo,
        users_gateway=users_gateway,
    )


def get_patch_reminder_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    reminder_repo: Annotated[IReminderRepository, Depends(get_reminder_repository)],
    users_gateway: Annotated[UsersPublicGateway, Depends(get_users_public_gateway)],
) -> PatchReminderUseCase:
    """Фабрика Use Case часткового оновлення нагадування (PATCH)."""
    return PatchReminderUseCase(
        uow=uow,
        reminder_repo=reminder_repo,
        users_gateway=users_gateway,
    )


def get_handle_reminder_action_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    reminder_repo: Annotated[IReminderRepository, Depends(get_reminder_repository)],
    medication_log_repo: Annotated[IMedicationLogRepository, Depends(get_medication_log_repository)],
    users_gateway: Annotated[UsersPublicGateway, Depends(get_users_public_gateway)],
) -> HandleReminderActionUseCase:
    """Фабрика Use Case обробки інтерактивних дій над нагадуванням."""
    return HandleReminderActionUseCase(
        uow=uow,
        reminder_repo=reminder_repo,
        medication_log_repo=medication_log_repo,
        users_gateway=users_gateway,
    )


def get_soft_delete_reminder_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    reminder_repo: Annotated[IReminderRepository, Depends(get_reminder_repository)],
) -> SoftDeleteReminderUseCase:
    """Фабрика Use Case м'якого видалення нагадування (Soft Delete)."""
    return SoftDeleteReminderUseCase(
        uow=uow,
        reminder_repo=reminder_repo,
    )


def get_hard_delete_reminder_use_case(
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
    reminder_repo: Annotated[IReminderRepository, Depends(get_reminder_repository)],
) -> HardDeleteReminderUseCase:
    """Фабрика Use Case фізичного видалення нагадування (Hard Delete)."""
    return HardDeleteReminderUseCase(
        uow=uow,
        reminder_repo=reminder_repo,
    )
