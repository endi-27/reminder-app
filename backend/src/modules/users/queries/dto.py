from datetime import datetime, time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.domain.enums import SystemRole
from src.modules.finance.public import ExchangeRateProvider


class UserSettingsResponseDTO(BaseModel):
    """DTO конфігурації налаштувань користувача."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[UUID, Field(description="Унікальний ідентифікатор запису налаштувань")]
    user_id: Annotated[UUID, Field(description="Ідентифікатор користувача")]
    timezone: Annotated[str, Field(description="Часовий пояс користувача у форматі IANA")]
    quiet_hours_start: Annotated[time, Field(description="Початок періоду тиші")]
    quiet_hours_end: Annotated[time, Field(description="Завершення періоду тиші")]
    preferred_bank: Annotated[
        ExchangeRateProvider,
        Field(description="Бажаний постачальник валютних курсів"),
    ]
    auto_deadline_priority_escalation: Annotated[
        bool,
        Field(description="Прапорець динамічної ескалації пріоритету задач"),
    ]
    version: Annotated[int, Field(description="Версія запису для оптимістичного блокування OCC")]
    created_at: Annotated[datetime, Field(description="Часова мітка створення (UTC)")]
    updated_at: Annotated[datetime, Field(description="Часова мітка останнього оновлення (UTC)")]


class TelegramAccountResponseDTO(BaseModel):
    """DTO реквізитів прив'язаного облікового запису Telegram."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[UUID, Field(description="Унікальний ідентифікатор профілю Telegram")]
    telegram_id: Annotated[int, Field(description="Числовий Telegram ID користувача")]
    telegram_chat_id: Annotated[int, Field(description="Ідентифікатор чату для надсилання сповіщень")]
    tg_username: Annotated[str | None, Field(default=None, description="Нікнейм у Telegram")] = None
    tg_full_name: Annotated[str | None, Field(default=None, description="Повне ім'я в Telegram")] = None
    version: Annotated[int, Field(description="Версія запису для оптимістичного блокування OCC")]


class UserResponseDTO(BaseModel):
    """DTO вихідних даних профілю користувача з налаштуваннями та Telegram-даними."""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[UUID, Field(description="UUIDv7 користувача")]
    username: Annotated[str, Field(description="Логін користувача")]
    role: Annotated[SystemRole, Field(description="Системна роль користувача")]
    telegram_account: Annotated[
        TelegramAccountResponseDTO | None,
        Field(default=None, description="Дані прив'язаного профілю Telegram"),
    ] = None
    settings: Annotated[
        UserSettingsResponseDTO,
        Field(description="Параметри налаштувань користувача"),
    ]
    version: Annotated[int, Field(description="Версія запису користувача (OCC)")]
    created_at: Annotated[datetime, Field(description="Дата створення акаунта (UTC)")]
    updated_at: Annotated[datetime, Field(description="Дата останньої зміни акаунта (UTC)")]


class UserNotificationContextDTO(BaseModel):
    """Компактний DTO контексту користувача для шедулера та сервісу доставки сповіщень."""

    model_config = ConfigDict(from_attributes=True)

    user_id: Annotated[UUID, Field(description="UUIDv7 користувача")]
    telegram_chat_id: Annotated[
        int | None,
        Field(default=None, description="Ідентифікатор чату Telegram для доставки сповіщень"),
    ] = None
    timezone: Annotated[str, Field(description="Часовий пояс користувача")]
    quiet_hours_start: Annotated[time, Field(description="Початок періоду тиші")]
    quiet_hours_end: Annotated[time, Field(description="Завершення періоду тиші")]
    preferred_bank: Annotated[
        ExchangeRateProvider,
        Field(description="Бажаний постачальник валютних курсів"),
    ]
    auto_deadline_priority_escalation: Annotated[
        bool,
        Field(description="Прапорець динамічної ескалації пріоритету задач"),
    ]
