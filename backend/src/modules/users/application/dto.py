from datetime import time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from src.core.domain.enums import SystemRole
from src.modules.finance.public import ExchangeRateProvider


class RegisterTelegramUserCommand(BaseModel):
    """Команда реєстрації або оновлення сесії користувача через Telegram-бота."""

    model_config = ConfigDict(extra="forbid")

    telegram_id: Annotated[
        int,
        Field(description="Унікальний числовий ідентифікатор користувача в Telegram"),
    ]
    telegram_chat_id: Annotated[
        int,
        Field(description="Ідентифікатор приватного діалогу або чату з ботом у Telegram"),
    ]
    tg_username: Annotated[
        str | None,
        Field(default=None, description="Нікнейм користувача в Telegram (без символу @)"),
    ] = None
    tg_full_name: Annotated[
        str | None,
        Field(default=None, description="Повне ім'я (First + Last Name) користувача в Telegram"),
    ] = None
    timezone: Annotated[
        str,
        Field(default="Europe/Kyiv", description="Ідентифікатор часового поясу IANA"),
    ] = "Europe/Kyiv"


class CreateUserCommand(BaseModel):
    """Команда створення нового облікового запису користувача."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str,
        Field(min_length=3, max_length=50, description="Унікальний логін користувача в системі"),
    ]
    password: Annotated[
        str | None,
        Field(default=None, min_length=6, description="Пароль облікового запису"),
    ] = None
    role: Annotated[
        SystemRole,
        Field(default=SystemRole.USER, description="Системна роль користувача"),
    ] = SystemRole.USER
    timezone: Annotated[
        str,
        Field(default="Europe/Kyiv", description="Бажаний часовий пояс користувача"),
    ] = "Europe/Kyiv"


class LoginCommand(BaseModel):
    """Команда входу в систему за логіном та паролем."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str,
        Field(min_length=1, description="Логін користувача"),
    ]
    password: Annotated[
        str,
        Field(min_length=1, description="Пароль облікового запису"),
    ]


class TokenResponseDTO(BaseModel):
    """DTO відповіді з access-токеном JWT після успішної автентифікації."""

    access_token: Annotated[
        str,
        Field(description="JWT токен доступу для авторизації в API"),
    ]
    token_type: Annotated[
        str,
        Field(default="bearer", description="Тип схеми авторизації токена"),
    ] = "bearer"
    expires_in: Annotated[
        int,
        Field(description="Термін дії токена в секундах"),
    ]


class UpdateUserSettingsCommand(BaseModel):
    """Команда точкового оновлення налаштувань користувача з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(description="Очікуваний номер версії сутності налаштувань (OCC)"),
    ]
    timezone: Annotated[
        str | None,
        Field(default=None, description="Новий ідентифікатор часового поясу IANA"),
    ] = None
    quiet_hours_start: Annotated[
        time | None,
        Field(default=None, description="Час початку періоду тиші (UTC або локальний час)"),
    ] = None
    quiet_hours_end: Annotated[
        time | None,
        Field(default=None, description="Час завершення періоду тиші (UTC або локальний час)"),
    ] = None
    preferred_bank: Annotated[
        ExchangeRateProvider | None,
        Field(default=None, description="Бажаний банк для отримання курсів валют"),
    ] = None
    auto_deadline_priority_escalation: Annotated[
        bool | None,
        Field(default=None, description="Прапорець автоматичної ескалації пріоритету дедлайнів"),
    ] = None
