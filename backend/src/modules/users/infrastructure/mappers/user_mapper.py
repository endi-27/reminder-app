from src.infrastructure.db.inspection import get_loaded
from src.infrastructure.db.mappers import BaseMapper
from src.modules.users.domain.models import User, UserSettings, UserTelegramAccount
from src.modules.users.infrastructure.models import (
    UserModel,
    UserSettingsModel,
    UserTelegramAccountModel,
)


class UserMapper(BaseMapper[User, UserModel]):
    """Мапер між доменним агрегатом User та ORM-моделями SQLAlchemy."""

    def to_domain(self, model: UserModel) -> User:
        """Трансформація ORM-моделі UserModel у доменний агрегат User."""
        telegram_account_orm = get_loaded(model, "telegram_account", None)
        telegram_account: UserTelegramAccount | None = None
        if telegram_account_orm is not None:
            telegram_account = UserTelegramAccount(
                id=telegram_account_orm.id,
                user_id=telegram_account_orm.user_id,
                telegram_id=telegram_account_orm.telegram_id,
                telegram_chat_id=telegram_account_orm.telegram_chat_id,
                tg_username=telegram_account_orm.tg_username,
                tg_full_name=telegram_account_orm.tg_full_name,
                version=telegram_account_orm.version,
                created_at=telegram_account_orm.created_at,
                updated_at=telegram_account_orm.updated_at,
            )

        settings_orm = get_loaded(model, "settings", None)
        settings: UserSettings | None = None
        if settings_orm is not None:
            settings = UserSettings(
                id=settings_orm.id,
                user_id=settings_orm.user_id,
                timezone=settings_orm.timezone,
                quiet_hours_start=settings_orm.quiet_hours_start,
                quiet_hours_end=settings_orm.quiet_hours_end,
                preferred_bank=settings_orm.preferred_bank,
                auto_deadline_priority_escalation=settings_orm.auto_deadline_priority_escalation,
                version=settings_orm.version,
                created_at=settings_orm.created_at,
                updated_at=settings_orm.updated_at,
            )
        else:
            settings = UserSettings.create_default(model.id)

        return User(
            id=model.id,
            username=model.username,
            role=model.role,
            password_hash=model.password_hash,
            telegram_account=telegram_account,
            settings=settings,
            version=model.version,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def to_model(self, entity: User) -> UserModel:
        """Трансформація доменного агрегата User в ORM-модель UserModel."""
        model = UserModel(
            id=entity.id,
            username=entity.username,
            role=entity.role,
            password_hash=entity.password_hash,
            version=entity.version,
            deleted_at=entity.deleted_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

        if entity.telegram_account is not None:
            tg = entity.telegram_account
            model.telegram_account = UserTelegramAccountModel(
                id=tg.id,
                user_id=tg.user_id,
                telegram_id=tg.telegram_id,
                telegram_chat_id=tg.telegram_chat_id,
                tg_username=tg.tg_username,
                tg_full_name=tg.tg_full_name,
                version=tg.version,
                created_at=tg.created_at,
                updated_at=tg.updated_at,
            )

        if entity.settings is not None:
            st = entity.settings
            model.settings = UserSettingsModel(
                id=st.id,
                user_id=st.user_id,
                timezone=st.timezone,
                quiet_hours_start=st.quiet_hours_start,
                quiet_hours_end=st.quiet_hours_end,
                preferred_bank=st.preferred_bank,
                auto_deadline_priority_escalation=st.auto_deadline_priority_escalation,
                version=st.version,
                created_at=st.created_at,
                updated_at=st.updated_at,
            )

        return model
