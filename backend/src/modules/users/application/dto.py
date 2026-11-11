from datetime import time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.domain.enums import SystemRole
from src.modules.finance.public import ExchangeRateProvider


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


class CreateUserCommand(BaseModel):
    """Команда створення нового облікового запису користувача через Web API."""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str,
        Field(min_length=3, max_length=50, description="Унікальний логін користувача в системі"),
    ]
    role: Annotated[
        SystemRole,
        Field(default=SystemRole.USER, description="Бажана системна роль (USER або ADMIN)"),
    ] = SystemRole.USER
    password: Annotated[
        str | None,
        Field(default=None, min_length=6, description="Опціональний пароль облікового запису"),
    ] = None
    timezone: Annotated[
        str,
        Field(default="Europe/Kyiv", description="Бажаний часовий пояс користувача IANA"),
    ] = "Europe/Kyiv"
    quiet_hours_start: Annotated[
        time | None,
        Field(default=None, description="Початок періоду тиші"),
    ] = None
    quiet_hours_end: Annotated[
        time | None,
        Field(default=None, description="Кінець періоду тиші"),
    ] = None
    preferred_bank: Annotated[
        ExchangeRateProvider | None,
        Field(default=None, description="Бажаний банк для курсів валют"),
    ] = None
    auto_deadline_priority_escalation: Annotated[
        bool | None,
        Field(default=None, description="Авто-ескалація дедлайнів"),
    ] = None


class RegisterTelegramUserCommand(BaseModel):
    """Команда реєстрації або отримання сесії користувача через Telegram-бота."""

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
        Field(default=None, description="Повне ім'я користувача в Telegram"),
    ] = None


class ChangePasswordAdminCommand(BaseModel):
    """Команда встановлення або скидання пароля користувачу адміністратором з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності користувача (OCC)"),
    ]
    new_password: Annotated[
        str,
        Field(min_length=6, description="Новий пароль облікового запису"),
    ]


class ChangeMyPasswordCommand(BaseModel):
    """Команда зміни власного пароля користувачем з верифікацією старого та контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності користувача (OCC)"),
    ]
    current_password: Annotated[
        str,
        Field(min_length=1, description="Поточний діючий пароль облікового запису"),
    ]
    new_password: Annotated[
        str,
        Field(min_length=6, description="Новий пароль облікового запису"),
    ]


class UpdateUserProfileAdminCommand(BaseModel):
    """Команда оновлення профілю користувача адміністратором з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності користувача (OCC)"),
    ]
    username: Annotated[
        str | None,
        Field(default=None, min_length=3, max_length=50, description="Новий логін користувача"),
    ] = None
    role: Annotated[
        SystemRole | None,
        Field(default=None, description="Нова системна роль користувача (USER або ADMIN)"),
    ] = None


class UpdateMyUsernameCommand(BaseModel):
    """Команда оновлення власного імені користувача з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності користувача (OCC)"),
    ]
    username: Annotated[
        str,
        Field(min_length=3, max_length=50, description="Новий бажаний логін користувача"),
    ]


class CreateTelegramAccountAdminCommand(BaseModel):
    """Команда створення нового запису Telegram-акаунта адміністратором (тільки SuperAdmin)."""

    model_config = ConfigDict(extra="forbid")

    telegram_id: Annotated[
        int,
        Field(gt=0, description="Унікальний числовий ідентифікатор користувача в Telegram"),
    ]
    telegram_chat_id: Annotated[
        int,
        Field(description="Ідентифікатор чату (діалогу з ботом чи групи) для надсилання повідомлень"),
    ]
    user_id: Annotated[
        UUID | None,
        Field(default=None, description="Опціональний UUID користувача для миттєвої прив'язки (1:1)"),
    ] = None
    tg_username: Annotated[
        str | None,
        Field(default=None, max_length=255, description="Нікнейм користувача у Telegram (без @)"),
    ] = None
    tg_full_name: Annotated[
        str | None,
        Field(default=None, max_length=255, description="Відображуване повне ім'я в Telegram"),
    ] = None


class UpdateTelegramAccountAdminCommand(BaseModel):
    """Команда оновлення даних Telegram-акаунта адміністратором з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності Telegram-акаунта (OCC)"),
    ]
    telegram_id: Annotated[
        int | None,
        Field(default=None, description="Новий числовий ідентифікатор Telegram ID"),
    ] = None
    telegram_chat_id: Annotated[
        int | None,
        Field(default=None, description="Новий числовий ідентифікатор Chat ID"),
    ] = None
    tg_username: Annotated[
        str | None,
        Field(default=None, description="Нікнейм у Telegram"),
    ] = None
    tg_full_name: Annotated[
        str | None,
        Field(default=None, description="Повне ім'я в Telegram"),
    ] = None


class UpdateMyTelegramAccountCommand(BaseModel):
    """Команда оновлення власних візуальних даних профілю Telegram з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності Telegram-акаунта (OCC)"),
    ]
    tg_username: Annotated[
        str | None,
        Field(default=None, description="Оновлений нікнейм у Telegram"),
    ] = None
    tg_full_name: Annotated[
        str | None,
        Field(default=None, description="Оновлене повне ім'я в Telegram"),
    ] = None


class LinkTelegramAccountCommand(BaseModel):
    """Команда прив'язки існуючого відв'язаного Telegram-акаунта до користувача з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності користувача (OCC)"),
    ]
    telegram_account_id: Annotated[
        UUID,
        Field(description="Унікальний ідентифікатор запису user_telegram_accounts (UUIDv7)"),
    ]


class UpdateUserSettingsCommand(BaseModel):
    """Команда оновлення налаштувань користувача з контролем версій (OCC)."""

    model_config = ConfigDict(extra="forbid")

    version: Annotated[
        int,
        Field(ge=1, description="Очікуваний номер версії сутності налаштувань (OCC)"),
    ]
    timezone: Annotated[
        str | None,
        Field(default=None, description="Новий ідентифікатор часового поясу IANA"),
    ] = None
    quiet_hours_start: Annotated[
        time | None,
        Field(default=None, description="Час початку періоду тиші"),
    ] = None
    quiet_hours_end: Annotated[
        time | None,
        Field(default=None, description="Час завершення періоду тиші"),
    ] = None
    preferred_bank: Annotated[
        ExchangeRateProvider | None,
        Field(default=None, description="Бажаний банк для отримання курсів валют"),
    ] = None
    auto_deadline_priority_escalation: Annotated[
        bool | None,
        Field(default=None, description="Прапорець автоматичної ескалації пріоритету дедлайнів"),
    ] = None
