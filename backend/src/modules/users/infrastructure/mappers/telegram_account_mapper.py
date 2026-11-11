from src.infrastructure.db.mappers import BaseMapper
from src.modules.users.domain.models import UserTelegramAccount
from src.modules.users.infrastructure.models import UserTelegramAccountModel


class TelegramAccountMapper(BaseMapper[UserTelegramAccount, UserTelegramAccountModel]):
    """Мапер між доменною сутністю UserTelegramAccount та ORM-моделлю UserTelegramAccountModel."""

    def to_domain(self, model: UserTelegramAccountModel) -> UserTelegramAccount:
        """Трансформація ORM-моделі у доменну сутність."""
        return UserTelegramAccount(
            id=model.id,
            user_id=model.user_id,
            telegram_id=model.telegram_id,
            telegram_chat_id=model.telegram_chat_id,
            tg_username=model.tg_username,
            tg_full_name=model.tg_full_name,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def to_model(self, entity: UserTelegramAccount) -> UserTelegramAccountModel:
        """Трансформація доменної сутності в ORM-модель."""
        return UserTelegramAccountModel(
            id=entity.id,
            user_id=entity.user_id,
            telegram_id=entity.telegram_id,
            telegram_chat_id=entity.telegram_chat_id,
            tg_username=entity.tg_username,
            tg_full_name=entity.tg_full_name,
            version=entity.version,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
