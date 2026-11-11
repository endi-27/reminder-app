import inspect
from collections.abc import Sequence
from datetime import time
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.infrastructure.db.queries import BaseQueryService
from src.modules.finance.public import ExchangeRateProvider
from src.modules.users.infrastructure.models import (
    UserModel,
    UserSettingsModel,
    UserTelegramAccountModel,
)
from src.modules.users.queries.dto import (
    TelegramAccountResponseDTO,
    UserNotificationContextDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)


class UserQueryService(BaseQueryService):
    """CQRS Read-Side сервіс вибірок даних користувачів без виконання операцій мутації."""

    def _map_user(self, model: UserModel) -> UserResponseDTO:
        """Трансформація ORM-моделі користувача з завантаженими зв'язками у вихідний DTO."""
        tg_dto: TelegramAccountResponseDTO | None = None
        if model.telegram_account is not None:
            tg_dto = TelegramAccountResponseDTO.model_validate(model.telegram_account)

        settings_dto = (
            UserSettingsResponseDTO.model_validate(model.settings)
            if model.settings is not None
            else UserSettingsResponseDTO(
                id=model.id,
                user_id=model.id,
                timezone="Europe/Kyiv",
                quiet_hours_start=time(23, 0),
                quiet_hours_end=time(8, 0),
                preferred_bank=ExchangeRateProvider.MONOBANK,
                auto_deadline_priority_escalation=True,
                version=1,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )
        )

        return UserResponseDTO(
            id=model.id,
            username=model.username,
            role=model.role,
            telegram_account=tg_dto,
            settings=settings_dto,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_by_id(self, user_id: UUID) -> UserResponseDTO | None:
        """Отримання профілю користувача за ідентифікатором UUID."""
        stmt = (
            select(UserModel)
            .options(
                joinedload(UserModel.telegram_account),
                joinedload(UserModel.settings),
            )
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        user_orm = result.scalar_one_or_none()
        if inspect.iscoroutine(user_orm):
            user_orm.close()
            return None
        if user_orm is None or not isinstance(user_orm, UserModel):
            return None
        return self._map_user(user_orm)

    async def get_by_telegram_id(self, telegram_id: int) -> UserResponseDTO | None:
        """Отримання профілю користувача за його Telegram ID."""
        stmt = (
            select(UserModel)
            .join(UserModel.telegram_account)
            .options(
                joinedload(UserModel.telegram_account),
                joinedload(UserModel.settings),
            )
            .where(
                UserTelegramAccountModel.telegram_id == telegram_id,
                UserModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        user_orm = result.scalar_one_or_none()
        if inspect.iscoroutine(user_orm):
            user_orm.close()
            return None
        if user_orm is None or not isinstance(user_orm, UserModel):
            return None
        return self._map_user(user_orm)

    async def get_settings_by_user_id(self, user_id: UUID) -> UserSettingsResponseDTO | None:
        """Отримання виключно налаштувань користувача за його ідентифікатором."""
        stmt = (
            select(UserSettingsModel)
            .join(UserModel, UserSettingsModel.user_id == UserModel.id)
            .where(UserSettingsModel.user_id == user_id, UserModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        settings_orm = result.scalar_one_or_none()
        if inspect.iscoroutine(settings_orm):
            settings_orm.close()
            return None
        if settings_orm is None or not isinstance(settings_orm, UserSettingsModel):
            return None
        return UserSettingsResponseDTO.model_validate(settings_orm)

    async def get_notification_context(self, user_id: UUID) -> UserNotificationContextDTO | None:
        """Отримання оптимізованого контексту сповіщень користувача для шедулера."""
        stmt = (
            select(
                UserModel.id.label("user_id"),
                UserTelegramAccountModel.telegram_chat_id.label("telegram_chat_id"),
                UserSettingsModel.timezone.label("timezone"),
                UserSettingsModel.quiet_hours_start.label("quiet_hours_start"),
                UserSettingsModel.quiet_hours_end.label("quiet_hours_end"),
                UserSettingsModel.preferred_bank.label("preferred_bank"),
                UserSettingsModel.auto_deadline_priority_escalation.label("auto_deadline_priority_escalation"),
            )
            .join(UserSettingsModel, UserSettingsModel.user_id == UserModel.id)
            .outerjoin(UserTelegramAccountModel, UserTelegramAccountModel.user_id == UserModel.id)
            .where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return None

        return UserNotificationContextDTO(
            user_id=row.user_id,
            telegram_chat_id=row.telegram_chat_id,
            timezone=row.timezone,
            quiet_hours_start=row.quiet_hours_start,
            quiet_hours_end=row.quiet_hours_end,
            preferred_bank=row.preferred_bank,
            auto_deadline_priority_escalation=row.auto_deadline_priority_escalation,
        )

    async def get_notification_contexts_by_ids(
        self,
        user_ids: Sequence[UUID],
    ) -> dict[UUID, UserNotificationContextDTO]:
        """
        Пакетне завантаження контекстів сповіщень для шедулера за один SQL-запит (без N+1).
        """
        if not user_ids:
            return {}

        stmt = (
            select(
                UserModel.id.label("user_id"),
                UserTelegramAccountModel.telegram_chat_id.label("telegram_chat_id"),
                UserSettingsModel.timezone.label("timezone"),
                UserSettingsModel.quiet_hours_start.label("quiet_hours_start"),
                UserSettingsModel.quiet_hours_end.label("quiet_hours_end"),
                UserSettingsModel.preferred_bank.label("preferred_bank"),
                UserSettingsModel.auto_deadline_priority_escalation.label("auto_deadline_priority_escalation"),
            )
            .join(UserSettingsModel, UserSettingsModel.user_id == UserModel.id)
            .outerjoin(UserTelegramAccountModel, UserTelegramAccountModel.user_id == UserModel.id)
            .where(UserModel.id.in_(user_ids), UserModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        contexts: dict[UUID, UserNotificationContextDTO] = {}
        for row in result.all():
            contexts[row.user_id] = UserNotificationContextDTO(
                user_id=row.user_id,
                telegram_chat_id=row.telegram_chat_id,
                timezone=row.timezone,
                quiet_hours_start=row.quiet_hours_start,
                quiet_hours_end=row.quiet_hours_end,
                preferred_bank=row.preferred_bank,
                auto_deadline_priority_escalation=row.auto_deadline_priority_escalation,
            )
        return contexts

    async def get_all(self, params: PaginationParams) -> PaginatedResponse[UserResponseDTO]:
        """Пагінована вибірка активних користувачів платформи для адміністративної панелі."""
        count_stmt = select(func.count(UserModel.id)).where(UserModel.deleted_at.is_(None))
        total = (await self._session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(UserModel)
            .options(
                joinedload(UserModel.telegram_account),
                joinedload(UserModel.settings),
            )
            .where(UserModel.deleted_at.is_(None))
            .order_by(UserModel.created_at.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        result = await self._session.execute(stmt)
        users = result.scalars().unique().all()

        items = [self._map_user(user) for user in users]
        return PaginatedResponse.create(items=items, total=total, params=params)
