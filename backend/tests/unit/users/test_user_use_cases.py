from datetime import time
from uuid import UUID

import pytest
from uuid6 import uuid7

from src.core.domain.enums import SystemRole
from src.core.exceptions import ForbiddenException, OptimisticLockConflictException
from src.core.security import CurrentUser, decode_token
from src.modules.users.application.dto import (
    ChangeMyPasswordCommand,
    ChangePasswordAdminCommand,
    CreateTelegramAccountAdminCommand,
    CreateUserCommand,
    LinkTelegramAccountCommand,
    LoginCommand,
    RegisterTelegramUserCommand,
    UpdateMyTelegramAccountCommand,
    UpdateMyUsernameCommand,
    UpdateTelegramAccountAdminCommand,
    UpdateUserProfileAdminCommand,
    UpdateUserSettingsCommand,
)
from src.modules.users.application.use_cases import (
    AuthenticateUserUseCase,
    ChangeMyPasswordUseCase,
    ChangePasswordAdminUseCase,
    CreateTelegramAccountAdminUseCase,
    CreateUserUseCase,
    GetOrCreateTelegramUserUseCase,
    HardDeleteTelegramAccountUseCase,
    HardDeleteUserUseCase,
    LinkTelegramAccountUseCase,
    ResetUserSettingsUseCase,
    RestoreUserUseCase,
    SoftDeleteUserUseCase,
    UnlinkTelegramAccountUseCase,
    UpdateMyTelegramAccountUseCase,
    UpdateMyUsernameUseCase,
    UpdateOtherUserSettingsUseCase,
    UpdateTelegramAccountAdminUseCase,
    UpdateUserProfileAdminUseCase,
    UpdateUserSettingsUseCase,
)
from src.modules.users.domain.exceptions import (
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    PasswordNotSetError,
    SelfActionForbiddenError,
    SuperAdminActionForbiddenError,
    SuperAdminAlreadyExistsError,
    TelegramAccountAlreadyExistsError,
    TelegramAccountAlreadyLinkedError,
    TelegramAccountInUseError,
    TelegramAccountNotLinkedError,
    UserAlreadyExistsError,
    UserDeactivatedError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import IUserRepository
from src.modules.users.domain.models import User, UserTelegramAccount
from tests.unit.fakes import FakePasswordHasher, FakeUnitOfWork


class InMemoryUserRepository(IUserRepository):
    """Швидкий тестовий дублер репозиторію користувачів у пам'яті."""

    def __init__(self, initial_users: list[User] | None = None) -> None:
        self.users: dict[UUID, User] = {u.id: u for u in (initial_users or [])}
        self.telegram_accounts: dict[UUID, UserTelegramAccount] = {}
        for u in self.users.values():
            if u.telegram_account is not None:
                self.telegram_accounts[u.telegram_account.id] = u.telegram_account

    async def get_by_id(self, entity_id: UUID) -> User | None:
        return self.users.get(entity_id)

    async def get_by_username(
        self,
        username: str,
    ) -> User | None:
        for user in self.users.values():
            if user.username == username:
                return user
        return None

    async def get_by_telegram_id(
        self,
        telegram_id: int,
    ) -> User | None:
        for user in self.users.values():
            if user.telegram_account is not None and user.telegram_account.telegram_id == telegram_id:
                return user
        return None

    async def exists_by_username(self, username: str) -> bool:
        return any(u.username == username for u in self.users.values())

    async def exists_super_admin(self) -> bool:
        return any(u.role == SystemRole.SUPER_ADMIN and u.is_active for u in self.users.values())

    async def save(self, entity: User, /) -> None:
        self.users[entity.id] = entity
        if entity.telegram_account is not None:
            self.telegram_accounts[entity.telegram_account.id] = entity.telegram_account

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        if entity_id in self.users:
            user = self.users[entity_id]
            if user.telegram_account is not None:
                self.telegram_accounts.pop(user.telegram_account.id, None)
            del self.users[entity_id]
            return True
        return False

    async def get_telegram_account_by_id(self, account_id: UUID) -> UserTelegramAccount | None:
        return self.telegram_accounts.get(account_id)

    async def get_telegram_account_by_tg_id(self, telegram_id: int) -> UserTelegramAccount | None:
        for acc in self.telegram_accounts.values():
            if acc.telegram_id == telegram_id:
                return acc
        return None

    async def get_telegram_account_by_chat_id(self, chat_id: int) -> UserTelegramAccount | None:
        for acc in self.telegram_accounts.values():
            if acc.telegram_chat_id == chat_id:
                return acc
        return None

    async def save_telegram_account(self, account: UserTelegramAccount, /) -> None:
        self.telegram_accounts[account.id] = account

    async def delete_telegram_account_by_id(self, account_id: UUID, /) -> bool:
        if account_id in self.telegram_accounts:
            del self.telegram_accounts[account_id]
            return True
        return False


class FakeRemindersGateway:
    """Фейковий шлюз модуля нагадувань для перевірки паузи нагадувань."""

    def __init__(self) -> None:
        self.paused_users: list[UUID] = []

    async def pause_deadline_tasks_by_user_id(self, user_id: UUID, *, uow: object = None) -> int:
        self.paused_users.append(user_id)
        return 1

    async def pause_all_active_reminders_by_user_id(self, user_id: UUID, *, uow: object = None) -> int:
        self.paused_users.append(user_id)
        return 1


# --- Сценарій 1: Авторизація ---
@pytest.mark.asyncio
async def test_authenticate_user_scenarios() -> None:
    repo = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    use_case = AuthenticateUserUseCase(user_repo=repo, password_hasher=hasher)

    user = User(
        id=uuid7(),
        username="alex",
        role=SystemRole.USER,
        password_hash=hasher.hash("secret123"),
    )
    user.link_or_update_telegram(telegram_id=1001, telegram_chat_id=1001)
    await repo.save(user)

    # 1. Успішний вхід
    token_dto = await use_case.execute(LoginCommand(username="alex", password="secret123"))
    assert token_dto.token_type == "bearer"
    payload = decode_token(token_dto.access_token)
    assert payload["sub"] == str(user.id)
    assert payload["username"] == "alex"
    assert hasher.dummy_verify_call_count == 0

    # 2. Невірний пароль для існуючого користувача
    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(LoginCommand(username="alex", password="wrong"))
    assert hasher.dummy_verify_call_count == 0

    # 3. Неіснуючий користувач (захист від timing attacks)
    with pytest.raises(InvalidCredentialsError):
        await use_case.execute(LoginCommand(username="ghost_user", password="secret123"))
    assert hasher.dummy_verify_call_count == 1

    # 4. Користувач без пароля (захист від timing attacks)
    no_pwd_user = User(id=uuid7(), username="nopwd", password_hash=None)
    await repo.save(no_pwd_user)
    with pytest.raises(PasswordNotSetError, match="Пароль не встановлено"):
        await use_case.execute(LoginCommand(username="nopwd", password="any"))
    assert hasher.dummy_verify_call_count == 2

    # 5. Деактивований користувач
    user.soft_delete()
    with pytest.raises(UserDeactivatedError):
        await use_case.execute(LoginCommand(username="alex", password="secret123"))


# --- Сценарій 2: Створення користувача через Web API ---
@pytest.mark.asyncio
async def test_create_user_scenarios() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    use_case = CreateUserUseCase(uow=uow, user_repo=repo, password_hasher=hasher)

    super_admin_actor = CurrentUser(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)
    admin_actor = CurrentUser(id=uuid7(), username="admin", role=SystemRole.ADMIN)

    # 1. Admin створює USER
    u1_id = await use_case.execute(
        creator=admin_actor,
        cmd=CreateUserCommand(username="john_doe", role=SystemRole.USER, password="password123"),
    )
    u1 = await repo.get_by_id(u1_id)
    assert u1 is not None
    assert u1.username == "john_doe"
    assert u1.role == SystemRole.USER

    # 2. Admin намагається створити ADMIN -> заборонено
    with pytest.raises(ForbiddenException):
        await use_case.execute(
            creator=admin_actor,
            cmd=CreateUserCommand(username="another_admin", role=SystemRole.ADMIN),
        )

    # 3. SuperAdmin створює ADMIN -> дозволено
    u2_id = await use_case.execute(
        creator=super_admin_actor,
        cmd=CreateUserCommand(username="manager", role=SystemRole.ADMIN),
    )
    u2 = await repo.get_by_id(u2_id)
    assert u2 is not None
    assert u2.role == SystemRole.ADMIN

    # 4. Спроба створення другого SUPER_ADMIN -> заборонено
    with pytest.raises(SuperAdminAlreadyExistsError):
        await use_case.execute(
            creator=super_admin_actor,
            cmd=CreateUserCommand(username="root2", role=SystemRole.SUPER_ADMIN),
        )

    # 5. Дублікат логіна
    with pytest.raises(UserAlreadyExistsError):
        await use_case.execute(
            creator=super_admin_actor,
            cmd=CreateUserCommand(username="john_doe"),
        )


# --- Сценарій 3: Get or Create через Telegram (/start) ---
@pytest.mark.asyncio
async def test_get_or_create_telegram_user_scenarios() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    use_case = GetOrCreateTelegramUserUseCase(uow=uow, user_repo=repo)

    # 1. Первинний старт -> створює tg_{id}
    u_id = await use_case.execute(
        RegisterTelegramUserCommand(
            telegram_id=777123,
            telegram_chat_id=777123,
            tg_username="some_nick",
            tg_full_name="Some Name",
        )
    )
    u = await repo.get_by_id(u_id)
    assert u is not None
    assert u.username == "tg_777123"
    assert u.telegram_account is not None
    assert u.telegram_account.telegram_id == 777123

    # 2. Повторний старт активного користувача -> оновлює реквізити
    u_updated_id = await use_case.execute(
        RegisterTelegramUserCommand(
            telegram_id=777123,
            telegram_chat_id=999999,
            tg_username="new_nick",
            tg_full_name="New Name",
        )
    )
    assert u_updated_id == u_id
    u_updated = await repo.get_by_id(u_updated_id)
    assert u_updated is not None
    assert u_updated.telegram_account is not None
    assert u_updated.telegram_account.telegram_chat_id == 999999

    # 3. Старт деактивованого користувача -> НЕ розблоковує, кидає помилку!
    u.soft_delete()
    await repo.save(u)
    with pytest.raises(UserDeactivatedError):
        await use_case.execute(
            RegisterTelegramUserCommand(
                telegram_id=777123,
                telegram_chat_id=999999,
            )
        )


# --- Сценарій 4 та 5: Прив'язати / Відв'язати Telegram ---
@pytest.mark.asyncio
async def test_link_and_unlink_telegram_account() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    link_uc = LinkTelegramAccountUseCase(uow=uow, user_repo=repo)
    unlink_uc = UnlinkTelegramAccountUseCase(uow=uow, user_repo=repo)

    user = User(id=uuid7(), username="dmitro")
    await repo.save(user)

    tg_acc = UserTelegramAccount(
        id=uuid7(),
        user_id=None,
        telegram_id=12345,
        telegram_chat_id=12345,
    )
    await repo.save_telegram_account(tg_acc)

    # 1. Прив'язка вільного акаунта
    await link_uc.execute(user.id, LinkTelegramAccountCommand(version=user.version, telegram_account_id=tg_acc.id))
    assert user.telegram_account is not None
    assert user.telegram_account.id == tg_acc.id
    assert tg_acc.user_id == user.id

    # 2. Конфлікт версії OCC при прив'язці
    with pytest.raises(OptimisticLockConflictException):
        await link_uc.execute(user.id, LinkTelegramAccountCommand(version=999, telegram_account_id=tg_acc.id))

    # 3. Спроба прив'язати ще один, коли вже є прив'язаний
    tg_acc2 = UserTelegramAccount(id=uuid7(), user_id=None, telegram_id=999, telegram_chat_id=999)
    await repo.save_telegram_account(tg_acc2)
    with pytest.raises(TelegramAccountAlreadyLinkedError):
        await link_uc.execute(user.id, LinkTelegramAccountCommand(version=user.version, telegram_account_id=tg_acc2.id))

    # 4. Відв'язування
    await unlink_uc.execute(user.id)
    assert user.telegram_account is None
    assert tg_acc.user_id is None

    # 5. Повторна відв'язка викликає помилку
    with pytest.raises(TelegramAccountNotLinkedError):
        await unlink_uc.execute(user.id)


# --- Сценарій 6 та 7: Зміна пароля комусь / собі ---
@pytest.mark.asyncio
async def test_change_password_use_cases() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    admin_uc = ChangePasswordAdminUseCase(uow=uow, user_repo=repo, password_hasher=hasher)
    my_uc = ChangeMyPasswordUseCase(uow=uow, user_repo=repo, password_hasher=hasher)

    super_admin = User(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)
    target_user = User(id=uuid7(), username="target", role=SystemRole.USER, password_hash=hasher.hash("old_pwd"))
    no_pwd_user = User(id=uuid7(), username="nopwd", role=SystemRole.USER, password_hash=None)
    await repo.save(super_admin)
    await repo.save(target_user)
    await repo.save(no_pwd_user)

    actor = CurrentUser(id=super_admin.id, username="root", role=SystemRole.SUPER_ADMIN)

    # 1. SuperAdmin змінює пароль користувачу
    await admin_uc.execute(
        actor,
        target_user.id,
        ChangePasswordAdminCommand(version=target_user.version, new_password="new_pwd_123"),
    )
    assert hasher.verify("new_pwd_123", target_user.password_hash or "")

    # Конфлікт OCC при зміні пароля адміністратором
    with pytest.raises(OptimisticLockConflictException):
        await admin_uc.execute(
            actor,
            target_user.id,
            ChangePasswordAdminCommand(version=999, new_password="another_pwd_123"),
        )

    # 2. SuperAdmin не може змінити пароль собі через адмін-роут
    with pytest.raises(SelfActionForbiddenError):
        await admin_uc.execute(
            actor,
            super_admin.id,
            ChangePasswordAdminCommand(version=super_admin.version, new_password="secret_pass"),
        )

    # 3. Користувач змінює пароль собі з правильним current_password
    await my_uc.execute(
        target_user.id,
        ChangeMyPasswordCommand(
            version=target_user.version,
            current_password="new_pwd_123",
            new_password="super_new_pwd",
        ),
    )
    assert hasher.verify("super_new_pwd", target_user.password_hash or "")

    # Конфлікт OCC при зміні власного пароля
    with pytest.raises(OptimisticLockConflictException):
        await my_uc.execute(
            target_user.id,
            ChangeMyPasswordCommand(version=999, current_password="super_new_pwd", new_password="another_pass"),
        )

    # 4. Користувач передає невірний current_password
    with pytest.raises(InvalidCurrentPasswordError):
        await my_uc.execute(
            target_user.id,
            ChangeMyPasswordCommand(version=target_user.version, current_password="wrong", new_password="another_pwd"),
        )

    # 5. Користувач без пароля намагається змінити собі пароль -> PasswordNotSetError
    with pytest.raises(PasswordNotSetError):
        await my_uc.execute(
            no_pwd_user.id,
            ChangeMyPasswordCommand(version=no_pwd_user.version, current_password="any", new_password="new_password"),
        )


# --- Сценарій 8 та 9: Зміна профілю комусь / собі ---
@pytest.mark.asyncio
async def test_update_profile_use_cases() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    admin_uc = UpdateUserProfileAdminUseCase(uow=uow, user_repo=repo)
    my_uc = UpdateMyUsernameUseCase(uow=uow, user_repo=repo)

    super_admin = User(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)
    user = User(id=uuid7(), username="bob", role=SystemRole.USER)
    await repo.save(super_admin)
    await repo.save(user)

    actor = CurrentUser(id=super_admin.id, username="root", role=SystemRole.SUPER_ADMIN)

    # 1. SuperAdmin змінює username та role іншому
    await admin_uc.execute(
        actor,
        user.id,
        UpdateUserProfileAdminCommand(version=user.version, username="bobby", role=SystemRole.ADMIN),
    )
    assert user.username == "bobby"
    assert user.role == SystemRole.ADMIN

    # Конфлікт OCC при зміні профілю адміном
    with pytest.raises(OptimisticLockConflictException):
        await admin_uc.execute(
            actor,
            user.id,
            UpdateUserProfileAdminCommand(version=999, username="new_bob"),
        )

    # 2. SuperAdmin намагається призначити роль SUPER_ADMIN -> заборонено
    with pytest.raises(SuperAdminAlreadyExistsError):
        await admin_uc.execute(
            actor,
            user.id,
            UpdateUserProfileAdminCommand(version=user.version, role=SystemRole.SUPER_ADMIN),
        )

    # 3. Зміна username собі
    await my_uc.execute(user.id, UpdateMyUsernameCommand(version=user.version, username="robert"))
    assert user.username == "robert"

    # Конфлікт OCC при зміні власного логіна
    with pytest.raises(OptimisticLockConflictException):
        await my_uc.execute(user.id, UpdateMyUsernameCommand(version=999, username="fail_bob"))


# --- Сценарій 10 та 11: Зміна даних Telegram комусь / собі ---
@pytest.mark.asyncio
async def test_update_telegram_account_use_cases() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    admin_uc = UpdateTelegramAccountAdminUseCase(uow=uow, user_repo=repo)
    my_uc = UpdateMyTelegramAccountUseCase(uow=uow, user_repo=repo)

    super_admin = User(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)
    super_admin.link_or_update_telegram(telegram_id=1, telegram_chat_id=1)
    user = User(id=uuid7(), username="alice")
    user.link_or_update_telegram(telegram_id=2, telegram_chat_id=2, tg_username="old_alice")
    await repo.save(super_admin)
    await repo.save(user)

    actor = CurrentUser(id=super_admin.id, username="root", role=SystemRole.SUPER_ADMIN)

    # 1. SuperAdmin змінює chat_id іншому користувачу
    target_acc = user.telegram_account
    assert target_acc is not None
    await admin_uc.execute(
        actor,
        target_acc.id,
        UpdateTelegramAccountAdminCommand(version=target_acc.version, telegram_chat_id=2222),
    )
    assert target_acc.telegram_chat_id == 2222

    # Конфлікт OCC при зміні Telegram-акаунта адміністратором
    with pytest.raises(OptimisticLockConflictException):
        await admin_uc.execute(
            actor,
            target_acc.id,
            UpdateTelegramAccountAdminCommand(version=999, telegram_chat_id=3333),
        )

    # 2. SuperAdmin намагається змінити власний TG акаунт через адмін-роут -> помилка
    own_acc = super_admin.telegram_account
    assert own_acc is not None
    with pytest.raises(SelfActionForbiddenError):
        await admin_uc.execute(
            actor,
            own_acc.id,
            UpdateTelegramAccountAdminCommand(version=own_acc.version, telegram_chat_id=1111),
        )

    # 3. Користувач змінює собі тільки візуальні поля
    await my_uc.execute(
        user.id,
        UpdateMyTelegramAccountCommand(
            version=target_acc.version,
            tg_username="new_alice",
            tg_full_name="Alice Wonder",
        ),
    )
    assert target_acc.tg_username == "new_alice"
    assert target_acc.tg_full_name == "Alice Wonder"

    # Конфлікт OCC при зміні свого Telegram-акаунта
    with pytest.raises(OptimisticLockConflictException):
        await my_uc.execute(
            user.id,
            UpdateMyTelegramAccountCommand(version=999, tg_username="fail_alice"),
        )


# --- Сценарій 12, 13, 14: Налаштування користувача ---
@pytest.mark.asyncio
async def test_user_settings_use_cases() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    admin_uc = UpdateOtherUserSettingsUseCase(uow=uow, user_repo=repo)
    my_uc = UpdateUserSettingsUseCase(uow=uow, user_repo=repo)
    reset_uc = ResetUserSettingsUseCase(uow=uow, user_repo=repo)

    admin = User(id=uuid7(), username="adm", role=SystemRole.ADMIN)
    user = User(id=uuid7(), username="user1")
    await repo.save(admin)
    await repo.save(user)

    actor = CurrentUser(id=admin.id, username="adm", role=SystemRole.ADMIN)

    # 1. Admin оновлює налаштування іншому
    await admin_uc.execute(
        actor,
        user.id,
        UpdateUserSettingsCommand(version=user.current_settings.version, timezone="Europe/Warsaw"),
    )
    assert user.current_settings.timezone == "Europe/Warsaw"

    # Конфлікт OCC при зміні налаштувань іншому
    with pytest.raises(OptimisticLockConflictException):
        await admin_uc.execute(
            actor,
            user.id,
            UpdateUserSettingsCommand(version=999, timezone="UTC"),
        )

    # 2. Користувач оновлює налаштування собі з OCC
    await my_uc.execute(
        user.id,
        UpdateUserSettingsCommand(version=user.current_settings.version, timezone="Europe/Kyiv"),
    )
    assert user.current_settings.timezone == "Europe/Kyiv"

    # 3. Конфлікт OCC
    with pytest.raises(OptimisticLockConflictException):
        await my_uc.execute(
            user.id,
            UpdateUserSettingsCommand(version=999, timezone="UTC"),
        )

    # 4. Скидання налаштувань собі
    user.update_settings(timezone="Europe/Berlin", quiet_hours_start=time(20, 0))
    await reset_uc.execute(user.id)
    assert user.current_settings.timezone == "Europe/Kyiv"
    assert user.current_settings.quiet_hours_start == time(23, 0)


# --- Сценарій 15, 16, 17: Soft Delete, Restore, Hard Delete ---
@pytest.mark.asyncio
async def test_soft_and_hard_delete_and_restore() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    reminders_gw = FakeRemindersGateway()
    soft_uc = SoftDeleteUserUseCase(uow=uow, user_repo=repo, reminders_gateway=reminders_gw)
    restore_uc = RestoreUserUseCase(uow=uow, user_repo=repo)
    hard_uc = HardDeleteUserUseCase(uow=uow, user_repo=repo)

    super_admin = User(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)
    user = User(id=uuid7(), username="todelete", role=SystemRole.USER)
    await repo.save(super_admin)
    await repo.save(user)

    admin_actor = CurrentUser(id=super_admin.id, username="root", role=SystemRole.SUPER_ADMIN)

    # 1. Soft delete не можна робити собі
    with pytest.raises(SelfActionForbiddenError):
        await soft_uc.execute(actor=admin_actor, target_user_id=super_admin.id)

    # 2. Soft delete не можна робити SuperAdmin
    user_actor = CurrentUser(id=user.id, username="todelete", role=SystemRole.ADMIN)
    with pytest.raises(SuperAdminActionForbiddenError):
        await soft_uc.execute(actor=user_actor, target_user_id=super_admin.id)

    # 3. Успішний Soft Delete (і виклик паузи дедлайн-задач за Варіантом 3)
    await soft_uc.execute(actor=admin_actor, target_user_id=user.id)
    assert user.is_active is False
    assert user.id in reminders_gw.paused_users

    # 4. Відновлення (Restore)
    await restore_uc.execute(user.id)
    assert user.is_active is True

    # 5. Hard delete
    await hard_uc.execute(actor=admin_actor, target_user_id=user.id)
    assert await repo.get_by_id(user.id) is None


# --- Сценарій 18: Hard Delete Telegram Account ---
@pytest.mark.asyncio
async def test_hard_delete_telegram_account_scenarios() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    use_case = HardDeleteTelegramAccountUseCase(uow=uow, user_repo=repo)

    # 1. Прив'язаний Telegram акаунт
    linked_acc = UserTelegramAccount(id=uuid7(), user_id=uuid7(), telegram_id=111, telegram_chat_id=111)
    await repo.save_telegram_account(linked_acc)

    # Спроба видалити прив'язаний -> TelegramAccountInUseError
    with pytest.raises(TelegramAccountInUseError):
        await use_case.execute(linked_acc.id)

    # 2. Відв'язаний Telegram акаунт
    unlinked_acc = UserTelegramAccount(id=uuid7(), user_id=None, telegram_id=222, telegram_chat_id=222)
    await repo.save_telegram_account(unlinked_acc)

    await use_case.execute(unlinked_acc.id)
    assert await repo.get_telegram_account_by_id(unlinked_acc.id) is None


# --- Сценарій створення Telegram-акаунта адміністратором (SuperAdmin) ---
@pytest.mark.asyncio
async def test_create_telegram_account_admin_scenarios() -> None:
    uow = FakeUnitOfWork()
    repo = InMemoryUserRepository()
    use_case = CreateTelegramAccountAdminUseCase(uow=uow, user_repo=repo)

    super_admin = CurrentUser(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)
    admin = CurrentUser(id=uuid7(), username="admin", role=SystemRole.ADMIN)

    # 1. Тільки SuperAdmin має право створювати
    with pytest.raises(ForbiddenException, match="Тільки SuperAdmin"):
        await use_case.execute(
            actor=admin,
            cmd=CreateTelegramAccountAdminCommand(telegram_id=123, telegram_chat_id=456),
        )

    # 2. Успішне створення відв'язаного акаунта з різними telegram_id та telegram_chat_id
    account_id = await use_case.execute(
        actor=super_admin,
        cmd=CreateTelegramAccountAdminCommand(
            telegram_id=1001,
            telegram_chat_id=-1001234567,
            tg_username="super_chat",
            tg_full_name="Super Group Chat",
        ),
    )
    account = await repo.get_telegram_account_by_id(account_id)
    assert account is not None
    assert account.telegram_id == 1001
    assert account.telegram_chat_id == -1001234567
    assert account.tg_username == "super_chat"
    assert account.user_id is None
    assert uow.committed is True

    # 3. Дублікат telegram_id
    with pytest.raises(TelegramAccountAlreadyExistsError, match="telegram_id 1001 вже зареєстровано"):
        await use_case.execute(
            actor=super_admin,
            cmd=CreateTelegramAccountAdminCommand(telegram_id=1001, telegram_chat_id=9999),
        )

    # 4. Дублікат telegram_chat_id
    with pytest.raises(TelegramAccountAlreadyExistsError, match="telegram_chat_id -1001234567 вже зареєстровано"):
        await use_case.execute(
            actor=super_admin,
            cmd=CreateTelegramAccountAdminCommand(telegram_id=2002, telegram_chat_id=-1001234567),
        )

    # 5. Створення з миттєвою прив'язкою до існуючого активного користувача
    user = User(id=uuid7(), username="alice")
    await repo.save(user)

    linked_acc_id = await use_case.execute(
        actor=super_admin,
        cmd=CreateTelegramAccountAdminCommand(
            telegram_id=3003,
            telegram_chat_id=3003,
            user_id=user.id,
        ),
    )
    linked_acc = await repo.get_telegram_account_by_id(linked_acc_id)
    assert linked_acc is not None
    assert linked_acc.user_id == user.id
    assert user.telegram_account is not None
    assert user.telegram_account.telegram_id == 3003

    # 6. Спроба прив'язати до користувача, у якого вже є Telegram-акаунт
    with pytest.raises(TelegramAccountAlreadyLinkedError):
        await use_case.execute(
            actor=super_admin,
            cmd=CreateTelegramAccountAdminCommand(
                telegram_id=4004,
                telegram_chat_id=4004,
                user_id=user.id,
            ),
        )

    # 7. Спроба прив'язати до неіснуючого користувача
    with pytest.raises(UserNotFoundError):
        await use_case.execute(
            actor=super_admin,
            cmd=CreateTelegramAccountAdminCommand(
                telegram_id=5005,
                telegram_chat_id=5005,
                user_id=uuid7(),
            ),
        )
