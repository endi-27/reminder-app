import asyncio
import sys
from pathlib import Path

# Додавання кореня бекенду до sys.path для автономного запуску скрипта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uuid6 import uuid7

from src.core import logger, settings
from src.core.database import async_session_factory
from src.core.security import BcryptPasswordHasher
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.modules.users.domain.enums import UserRole
from src.modules.users.domain.models import User, UserSettings
from src.modules.users.infrastructure.repository import SqlAlchemyUserRepository


async def seed_superadmin() -> None:
    """Ідемпотентне створення первинного облікового запису SuperAdmin."""
    username = settings.seed.superadmin_username
    password = settings.seed.superadmin_password

    async with async_session_factory() as session:
        uow = SqlAlchemyUnitOfWork(session=session)
        user_repo = SqlAlchemyUserRepository(session=session)
        hasher = BcryptPasswordHasher(default_rounds=settings.auth.bcrypt_rounds)

        existing = await user_repo.get_by_username(username, include_deleted=True)
        if existing is not None:
            logger.info(
                "Обліковий запис SuperAdmin '{username}' вже існує. Сідування пропущено.",
                username=username,
            )
            return

        user_id = uuid7()
        user_settings = UserSettings.create_default(user_id)
        hashed_password = hasher.hash(password)

        superadmin = User(
            id=user_id,
            username=username,
            role=UserRole.SUPER_ADMIN,
            password_hash=hashed_password,
            settings=user_settings,
        )

        await user_repo.save(superadmin)
        await uow.commit()

        logger.info(
            "Успішно створено початкового користувача SuperAdmin '{username}' з ID: {user_id}",
            username=username,
            user_id=user_id,
        )


if __name__ == "__main__":
    asyncio.run(seed_superadmin())
