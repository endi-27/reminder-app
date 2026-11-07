from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.api.dependencies import CurrentUserDep
from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.modules.reminders.application.dto import (
    CreateReminderCommand,
    PatchReminderCommand,
    ReminderActionCommand,
    UpdateReminderCommand,
)
from src.modules.reminders.application.use_cases.create_reminder import (
    CreateReminderUseCase,
)
from src.modules.reminders.application.use_cases.delete_reminder import (
    HardDeleteReminderUseCase,
    SoftDeleteReminderUseCase,
)
from src.modules.reminders.application.use_cases.handle_reminder_action import (
    HandleReminderActionUseCase,
)
from src.modules.reminders.application.use_cases.update_reminder import (
    PatchReminderUseCase,
    UpdateReminderUseCase,
)
from src.modules.reminders.dependencies import (
    get_create_reminder_use_case,
    get_handle_reminder_action_use_case,
    get_hard_delete_reminder_use_case,
    get_patch_reminder_use_case,
    get_reminder_query_service,
    get_soft_delete_reminder_use_case,
    get_update_reminder_use_case,
)
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType
from src.modules.reminders.domain.exceptions import ReminderNotFoundError
from src.modules.reminders.queries.dto import (
    MedicationAdherenceStatsDTO,
    ReminderResponseDTO,
)
from src.modules.reminders.queries.query_service import ReminderQueryService

reminders_router = APIRouter(prefix="/reminders", tags=["Reminders"])


@reminders_router.post(
    "",
    response_model=ReminderResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Створення нового нагадування",
    description="Створює нагадування будь-якого з 5 підтримуваних типів із валідацією сумісності розкладу.",
)
async def create_reminder(
    cmd: CreateReminderCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[CreateReminderUseCase, Depends(get_create_reminder_use_case)],
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
) -> ReminderResponseDTO:
    """Створює нове нагадування користувача з розрахунком початкового моменту next_trigger_at."""
    reminder = await use_case.execute(user_id=current_user.id, cmd=cmd)
    dto = await query_service.get_by_id(reminder.id)
    if dto is None:
        raise ReminderNotFoundError("Не вдалося завантажити створене нагадування.")
    return dto


@reminders_router.get(
    "",
    response_model=PaginatedResponse[ReminderResponseDTO],
    summary="Отримання списку нагадувань користувача",
    description="Повертає пагінований список активних нагадувань із можливістю фільтрації за типом та статусом.",
)
async def list_reminders(
    current_user: CurrentUserDep,
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
    page: Annotated[int, Query(ge=1, description="Номер сторінки (від 1)")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Розмір сторінки (до 100)")] = 20,
    reminder_type: Annotated[ReminderType | None, Query(description="Фільтр за типом нагадування")] = None,
    status_filter: Annotated[ReminderStatus | None, Query(alias="status", description="Фільтр за статусом")] = None,
) -> PaginatedResponse[ReminderResponseDTO]:
    """Пагінована вибірка нагадувань поточного авторизованого користувача."""
    params = PaginationParams(page=page, size=size)
    return await query_service.list_for_user(
        user_id=current_user.id,
        params=params,
        reminder_type=reminder_type,
        status=status_filter,
    )


@reminders_router.get(
    "/{reminder_id}",
    response_model=ReminderResponseDTO,
    summary="Отримання деталей нагадування за ID",
    description="Повертає повну інформацію про конкретне нагадування користувача.",
)
async def get_reminder(
    reminder_id: UUID,
    current_user: CurrentUserDep,
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
) -> ReminderResponseDTO:
    """Отримує нагадування за його UUIDv7."""
    dto = await query_service.get_by_id(reminder_id=reminder_id, user_id=current_user.id)
    if dto is None:
        raise ReminderNotFoundError("Нагадування не знайдено.")
    return dto


@reminders_router.put(
    "/{reminder_id}",
    response_model=ReminderResponseDTO,
    summary="Повне оновлення нагадування (Full Update)",
    description="Повний перезапис усіх параметрів нагадування з перевіркою версії (OCC).",
)
async def update_reminder(
    reminder_id: UUID,
    cmd: UpdateReminderCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[UpdateReminderUseCase, Depends(get_update_reminder_use_case)],
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
) -> ReminderResponseDTO:
    """Виконує повне оновлення нагадування методом PUT."""
    await use_case.execute(reminder_id=reminder_id, user_id=current_user.id, cmd=cmd)
    dto = await query_service.get_by_id(reminder_id)
    if dto is None:
        raise ReminderNotFoundError("Нагадування не знайдено після оновлення.")
    return dto


@reminders_router.patch(
    "/{reminder_id}",
    response_model=ReminderResponseDTO,
    summary="Часткове оновлення нагадування (Partial Update)",
    description="Точкове оновлення окремих атрибутів нагадування з перевіркою версії (OCC).",
)
async def patch_reminder(
    reminder_id: UUID,
    cmd: PatchReminderCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[PatchReminderUseCase, Depends(get_patch_reminder_use_case)],
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
) -> ReminderResponseDTO:
    """Виконує часткове оновлення окремих полів нагадування методом PATCH."""
    await use_case.execute(reminder_id=reminder_id, user_id=current_user.id, cmd=cmd)
    dto = await query_service.get_by_id(reminder_id)
    if dto is None:
        raise ReminderNotFoundError("Нагадування не знайдено після оновлення.")
    return dto


@reminders_router.post(
    "/{reminder_id}/actions",
    response_model=ReminderResponseDTO,
    summary="Виконання інтерактивної дії над нагадуванням",
    description="RPC-ендпоінт для дій користувача: завершення, відкладення, пауза, списання підписки тощо.",
)
async def handle_reminder_action(
    reminder_id: UUID,
    cmd: ReminderActionCommand,
    current_user: CurrentUserDep,
    use_case: Annotated[HandleReminderActionUseCase, Depends(get_handle_reminder_action_use_case)],
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
) -> ReminderResponseDTO:
    """Обробляє інтерактивні RPC-дії користувача або бота над нагадуванням."""
    await use_case.execute(reminder_id=reminder_id, user_id=current_user.id, cmd=cmd)
    dto = await query_service.get_by_id(reminder_id)
    if dto is None:
        raise ReminderNotFoundError("Нагадування не знайдено після виконання дії.")
    return dto


@reminders_router.get(
    "/{reminder_id}/medication-logs",
    response_model=MedicationAdherenceStatsDTO,
    summary="Статистика прийому лікарського засобу",
    description="Повертає історію відміток та відсоток комплаєнсу (дотримання графіка) пацієнта.",
)
async def get_medication_logs(
    reminder_id: UUID,
    current_user: CurrentUserDep,
    query_service: Annotated[ReminderQueryService, Depends(get_reminder_query_service)],
) -> MedicationAdherenceStatsDTO:
    """Отримує статистику та журнал прийомів медикаменту."""
    return await query_service.get_medication_adherence(reminder_id=reminder_id, user_id=current_user.id)


@reminders_router.delete(
    "/{reminder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалення нагадування",
    description="Виконує м'яке (Soft Delete) або повне фізичне (Hard Delete) видалення нагадування.",
)
async def delete_reminder(
    reminder_id: UUID,
    current_user: CurrentUserDep,
    soft_use_case: Annotated[SoftDeleteReminderUseCase, Depends(get_soft_delete_reminder_use_case)],
    hard_use_case: Annotated[HardDeleteReminderUseCase, Depends(get_hard_delete_reminder_use_case)],
    hard: Annotated[bool, Query(description="Прапорець остаточного фізичного видалення")] = False,
) -> Response:
    """Видаляє нагадування користувача за його ідентифікатором."""
    if hard:
        await hard_use_case.execute(reminder_id=reminder_id, user_id=current_user.id)
    else:
        await soft_use_case.execute(reminder_id=reminder_id, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
