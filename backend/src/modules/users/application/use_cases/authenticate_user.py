from src.core.config import settings
from src.core.protocols import IPasswordHasher
from src.core.security import create_access_token
from src.modules.users.application.dto import LoginCommand, TokenResponseDTO
from src.modules.users.domain.exceptions import (
    InvalidCredentialsError,
    PasswordNotSetError,
    UserDeactivatedError,
)
from src.modules.users.domain.interfaces import IUserRepository


class AuthenticateUserUseCase:
    """Use Case автентифікації користувача та видачі JWT access-токена"""

    def __init__(
        self,
        user_repo: IUserRepository,
        password_hasher: IPasswordHasher,
    ) -> None:
        self._user_repo = user_repo
        self._hasher = password_hasher

    async def execute(self, cmd: LoginCommand) -> TokenResponseDTO:
        """Перевіряє облікові дані та повертає підписаний JWT access-токен."""
        user = await self._user_repo.get_by_username(cmd.username)

        if user is None:
            self._hasher.dummy_verify(cmd.password)
            raise InvalidCredentialsError("Невірний логін або пароль.")

        if not user.is_active:
            raise UserDeactivatedError("Обліковий запис деактивовано. Зверніться до адміністратора.")

        if user.password_hash is None:
            self._hasher.dummy_verify(cmd.password)
            raise PasswordNotSetError("Пароль не встановлено. Зверніться до адміністратора, щоб він його встановив.")

        if not self._hasher.verify(cmd.password, user.password_hash):
            raise InvalidCredentialsError("Невірний логін або пароль.")

        token_payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
            "telegram_id": (user.telegram_account.telegram_id if user.telegram_account is not None else None),
        }
        access_token = create_access_token(token_payload)
        expires_in = settings.auth.access_token_expire_minutes * 60

        return TokenResponseDTO(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
        )
