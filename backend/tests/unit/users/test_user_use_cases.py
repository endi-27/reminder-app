from datetime import time
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core.exceptions import OptimisticLockConflictException
from src.core.security import decode_token
from src.modules.users.application.dto import (
    CreateUserCommand,
    LoginCommand,
    RegisterTelegramUserCommand,
    UpdateUserSettingsCommand,
)
from src.modules.users.application.use_cases import (
    AuthenticateUserUseCase,
    CreateUserUseCase,
    GetOrCreateTelegramUserUseCase,
    HardDeleteUserUseCase,
    SoftDeleteUserUseCase,
    UpdateUserSettingsUseCase,
)
from src.modules.users.domain.enums import ExchangeRateProvider, UserRole
from src.modules.users.domain.exceptions import (
    InvalidCredentialsError,
    SuperAdminDeletionForbiddenError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User
from tests.unit.fakes import FakePasswordHasher, FakeUnitOfWork


class InMemoryUserRepository(IUserRepository):
    """Швидкий тестовий дублер репозиторію користувачів у пам'яті."""

    def __init__(self, initial_users: list[User] | None = None) -> None:
        self.users: dict[UUID, User] = {u.id: u for u in (initial_users or [])}

    async def get_by_id(self, entity_id: UUID, *, include_deleted: bool = False) -> User | None:
        user = self.users.get(entity_id)
        if user is None:
            return None
        if not include_deleted and not user.is_active:
            return None
        return user

    async def get_by_username(
        self,
        username: str,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        for user in self.users.values():
            if user.username == username:
                if not include_deleted and not user.is_active:
                    return None
                return user
        return None

    async def get_by_telegram_id(
        self,
        telegram_id: int,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        for user in self.users.values():
            if user.telegram_account is not None and user.telegram_account.telegram_id == telegram_id:
                if not include_deleted and not user.is_active:
                    return None
                return user
        return None

    async def exists_by_username(self, username: str) -> bool:
        return any(u.username == username for u in self.users.values())

    async def save(self, entity: User, /) -> None:
        self.users[entity.id] = entity

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        if entity_id in self.users:
            del self.users[entity_id]
            return True
        return False


@pytest.mark.asyncio
async def test_get_or_create_telegram_user_new_user() -> None:
    """Тест автоматичної реєстрації нового користувача при першому контакті з Telegram-ботом."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    use_case = GetOrCreateTelegramUserUseCase(uow=uow, user_repo=repo)

    cmd = RegisterTelegramUserCommand(
        telegram_id=111222333,
        telegram_chat_id=111222333,
        tg_username="developer_pro",
        tg_full_name="Ivan Petrov",
        timezone="Europe/Kyiv",
    )

    user = await use_case.execute(cmd)

    assert user is not None
    assert user.username == "developer_pro"
    assert user.telegram_account is not None
    assert user.telegram_account.telegram_id == 111222333
    assert user.current_settings.timezone == "Europe/Kyiv"
    assert uow.committed is True
    assert repo.users[user.id] == user


@pytest.mark.asyncio
async def test_get_or_create_telegram_user_existing_user_update() -> None:
    """Тест оновлення реквізитів існуючого Telegram-користувача без дублювання записів."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    use_case = GetOrCreateTelegramUserUseCase(uow=uow, user_repo=repo)

    # 1. Первинна реєстрація
    cmd1 = RegisterTelegramUserCommand(
        telegram_id=444555666,
        telegram_chat_id=444555666,
        tg_username="old_nick",
        tg_full_name="Old Name",
    )
    first_user = await use_case.execute(cmd1)

    # 2. Повторна синхронізація зі зміною нікнейму та чату
    cmd2 = RegisterTelegramUserCommand(
        telegram_id=444555666,
        telegram_chat_id=999888777,
        tg_username="new_nick",
        tg_full_name="New Name",
    )
    second_user = await use_case.execute(cmd2)

    assert first_user.id == second_user.id
    assert len(repo.users) == 1
    assert second_user.telegram_account is not None
    assert second_user.telegram_account.telegram_chat_id == 999888777
    assert second_user.telegram_account.tg_username == "new_nick"
    assert second_user.telegram_account.tg_full_name == "New Name"


@pytest.mark.asyncio
async def test_get_or_create_telegram_user_username_collision() -> None:
    """Тест обробки колізії логіна при реєстрації через Telegram."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    # Існуючий користувач уже зайняв логін "john"
    existing_user = User(id=uuid7(), username="john")
    await repo.save(existing_user)

    use_case = GetOrCreateTelegramUserUseCase(uow=uow, user_repo=repo)

    cmd = RegisterTelegramUserCommand(
        telegram_id=777888999,
        telegram_chat_id=777888999,
        tg_username="john",
        tg_full_name="John Doe",
    )
    new_user = await use_case.execute(cmd)

    # Логін повинен бути унікальним із суфіксом Telegram ID
    assert new_user.username == "john_777888999"
    assert new_user.id != existing_user.id


@pytest.mark.asyncio
async def test_get_or_create_telegram_user_restore_soft_deleted() -> None:
    """Тест автоматичного відновлення деактивованого акаунта при поверненні в бота."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    user = User(id=uuid7(), username="deleted_guy")
    user.link_or_update_telegram(telegram_id=555, telegram_chat_id=555)
    user.soft_delete()
    assert user.is_active is False
    await repo.save(user)

    use_case = GetOrCreateTelegramUserUseCase(uow=uow, user_repo=repo)
    cmd = RegisterTelegramUserCommand(
        telegram_id=555,
        telegram_chat_id=555,
        tg_username="active_again",
    )
    restored_user = await use_case.execute(cmd)

    assert restored_user.id == user.id
    assert restored_user.is_active is True
    assert restored_user.deleted_at is None


@pytest.mark.asyncio
async def test_create_user_success_and_duplicate() -> None:
    """Тест створення користувача та захисту від дублікатів логінів."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    use_case = CreateUserUseCase(uow=uow, user_repo=repo, password_hasher=hasher)

    cmd = CreateUserCommand(
        username="marta",
        password="secret_password",
        role=UserRole.ADMIN,
        timezone="Europe/Kyiv",
    )
    created_user = await use_case.execute(cmd)

    assert created_user.username == "marta"
    assert created_user.role == UserRole.ADMIN
    assert created_user.password_hash == "hashed_secret_password"
    assert created_user.current_settings.timezone == "Europe/Kyiv"
    assert uow.committed is True

    # Спроба створення користувача з тим самим логіном
    with pytest.raises(UserAlreadyExistsError, match="вже існує"):
        await use_case.execute(cmd)


@pytest.mark.asyncio
async def test_authenticate_user_success_and_failures() -> None:
    """Тест перевірки автентифікації користувача та валідації виданого JWT-токена."""
    repo = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    use_case = AuthenticateUserUseCase(user_repo=repo, password_hasher=hasher)

    user_id = uuid7()
    user = User(
        id=user_id,
        username="alex",
        role=UserRole.USER,
        password_hash=hasher.hash("correct_password"),
    )
    user.link_or_update_telegram(telegram_id=123123, telegram_chat_id=123123)
    await repo.save(user)

    # 1. Успішний вхід
    token_dto = await use_case.execute(LoginCommand(username="alex", password="correct_password"))
    assert token_dto.token_type == "bearer"
    assert token_dto.access_token is not None

    # Декодування токена та перевірка клеймів
    payload = decode_token(token_dto.access_token)
    assert payload["sub"] == str(user_id)
    assert payload["username"] == "alex"
    assert payload["role"] == "USER"
    assert payload["telegram_id"] == 123123

    # 2. Невірний пароль
    with pytest.raises(InvalidCredentialsError, match="Невірний логін або пароль"):
        await use_case.execute(LoginCommand(username="alex", password="wrong_password"))

    # 3. Неіснуючий логін
    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(LoginCommand(username="non_existent", password="pwd"))

    # 4. Деактивований користувач
    user.soft_delete()
    with pytest.raises(InvalidCredentialsError, match="деактивовано"):
        await use_case.execute(LoginCommand(username="alex", password="correct_password"))


@pytest.mark.asyncio
async def test_update_user_settings_occ_conflict() -> None:
    """Тест контролю версій (OCC) при оновленні налаштувань користувача."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    use_case = UpdateUserSettingsUseCase(uow=uow, user_repo=repo)

    user_id = uuid7()
    user = User(id=user_id, username="mark")
    user.current_settings.version = 1
    await repo.save(user)

    # Успішне оновлення з точною версією
    cmd = UpdateUserSettingsCommand(
        version=1,
        timezone="Europe/Rome",
        quiet_hours_start=time(21, 0),
        preferred_bank=ExchangeRateProvider.MONOBANK,
    )
    updated = await use_case.execute(user_id=user_id, cmd=cmd)
    assert updated.timezone == "Europe/Rome"
    assert updated.quiet_hours_start == time(21, 0)
    assert uow.committed is True

    # Конфлікт версії (передано версію 1, хоча актуальна змінилася або не збігається)
    conflict_cmd = UpdateUserSettingsCommand(
        version=99,
        timezone="UTC",
    )
    with pytest.raises(OptimisticLockConflictException):
        await use_case.execute(user_id=user_id, cmd=conflict_cmd)


@pytest.mark.asyncio
async def test_delete_user_use_cases() -> None:
    """Тест Use Cases м'якого та фізичного видалення акаунта."""
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    soft_uc = SoftDeleteUserUseCase(uow=uow, user_repo=repo)
    hard_uc = HardDeleteUserUseCase(uow=uow, user_repo=repo)

    super_admin = User(id=uuid7(), username="superadmin", role=UserRole.SUPER_ADMIN)
    regular_user = User(id=uuid7(), username="regular", role=UserRole.USER)
    await repo.save(super_admin)
    await repo.save(regular_user)

    # 1. Захист SuperAdmin від Soft Delete
    with pytest.raises(SuperAdminDeletionForbiddenError):
        await soft_uc.execute(super_admin.id)

    # 2. Захист SuperAdmin від Hard Delete
    with pytest.raises(SuperAdminDeletionForbiddenError):
        await hard_uc.execute(super_admin.id)

    # 3. Успішний Soft Delete звичайного користувача
    await soft_uc.execute(regular_user.id)
    assert regular_user.is_active is False
    assert await repo.get_by_id(regular_user.id) is None
    assert await repo.get_by_id(regular_user.id, include_deleted=True) is not None

    # 4. Успішний Hard Delete звичайного користувача
    await hard_uc.execute(regular_user.id)
    assert await repo.get_by_id(regular_user.id, include_deleted=True) is None

    # 5. Видалення неіснуючого ID викликає UserNotFoundError
    with pytest.raises(UserNotFoundError):
        await soft_uc.execute(uuid7())
