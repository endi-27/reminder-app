import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import bcrypt
import jwt
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import get_settings, settings
from src.core.domain.enums import ClientEnvironment, SystemRole
from src.core.protocols import IPasswordHasher


class CurrentUser(BaseModel):
    """Контекст поточного автентифікованого користувача"""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: Annotated[UUID, Field(description="UUIDv7 користувача")]
    username: Annotated[str, Field(description="Системний логін")]
    role: Annotated[SystemRole, Field(description="Системна роль")] = SystemRole.USER
    telegram_id: Annotated[int | None, Field(description="Telegram ID користувача")] = None
    environment: Annotated[
        ClientEnvironment,
        Field(description="Середовище виклику запиту (WEB_API або TELEGRAM_BOT)"),
    ] = ClientEnvironment.WEB_API

    @property
    def is_super_admin(self) -> bool:
        """Прапорець суперадміністратора платформи."""
        return self.role == SystemRole.SUPER_ADMIN

    @property
    def is_admin(self) -> bool:
        """Прапорець адміністративного доступу (SuperAdmin або Admin)."""
        return self.role in (SystemRole.SUPER_ADMIN, SystemRole.ADMIN)


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Генерація короткоживучого JWT access-токена з клеймами exp та iat."""
    now = datetime.now(UTC)
    to_encode = data.copy()
    expire = now + (expires_delta or timedelta(minutes=settings.auth.access_token_expire_minutes))
    to_encode.update({"iat": now, "exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.auth.access_secret_key, algorithm=settings.auth.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Декодування та перевірка валідності JWT-токена."""
    return jwt.decode(
        token,
        settings.auth.access_secret_key,
        algorithms=[settings.auth.algorithm],
    )


def verify_internal_token(token: str) -> bool:
    """Безпечна перевірка внутрішнього токена бота на основі secrets.compare_digest."""
    return secrets.compare_digest(token, settings.auth.internal_token)


class BcryptPasswordHasher(IPasswordHasher):
    """Реалізація IPasswordHasher на базі бібліотеки bcrypt."""

    _DEFAULT_DUMMY_HASH = "$2b$12$yhUD9CLBLSXk7XHKitO3w.QoWf6F37jTd/xgUlIMtZBtYzBK0Y4Sa"

    def __init__(self, default_rounds: int | None = None) -> None:
        self._default_rounds = default_rounds
        self._dummy_hashes: dict[int, str] = {
            12: self._DEFAULT_DUMMY_HASH,
            4: "$2b$04$brUYOx8c6NiQm0YtSr//6.OT.aU0XfGCX..gqfG0Fs3y9nKtuFShS",
        }

    def hash(self, password: str, rounds: int | None = None) -> str:
        """Створення криптографічного хешу пароля за допомогою bcrypt."""
        cost = rounds if rounds is not None else (self._default_rounds or get_settings().auth.bcrypt_rounds)
        salt = bcrypt.gensalt(rounds=cost)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """Перевірка відповідності відкритого пароля збереженому хешу."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    def dummy_verify(self, plain_password: str) -> bool:
        """Фіктивна перевірка пароля з константним часом для запобігання timing attacks."""
        cost = self._default_rounds or get_settings().auth.bcrypt_rounds
        dummy_hash = self._dummy_hashes.get(cost)
        if dummy_hash is None:
            salt = bcrypt.gensalt(rounds=cost)
            dummy_hash = bcrypt.hashpw(b"dummy_timing_protection_secret", salt).decode("utf-8")
            self._dummy_hashes[cost] = dummy_hash
        self.verify(plain_password, dummy_hash)
        return False


default_password_hasher: IPasswordHasher = BcryptPasswordHasher()
