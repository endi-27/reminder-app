from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx

from src.api.schemas.pagination import PaginatedResponse
from src.bot.client.exceptions import (
    BotApiConflictError,
    BotApiError,
    BotApiNotFoundError,
    BotApiValidationError,
)
from src.core import logger
from src.core.config import settings
from src.modules.finance.queries.dto import ExchangeRateResponseDTO
from src.modules.reminders.application.dto import (
    CreateReminderCommand,
    PatchReminderCommand,
    ReminderActionCommand,
)
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType
from src.modules.reminders.queries.dto import (
    MedicationAdherenceStatsDTO,
    ReminderResponseDTO,
)
from src.modules.users.application.dto import (
    RegisterTelegramUserCommand,
    UpdateUserSettingsCommand,
)
from src.modules.users.queries.dto import (
    UserResponseDTO,
    UserSettingsResponseDTO,
)


class BackendApiClient:
    """Асинхронний HTTP-клієнт для взаємодії Telegram-бота з REST API бекенду."""

    def __init__(
        self,
        base_url: str | None = None,
        internal_token: str | None = None,
        timeout: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or settings.bot.backend_api_url).rstrip("/")
        self._internal_token = internal_token or settings.auth.internal_token
        self._timeout = timeout

        if http_client is not None:
            self._client = http_client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(timeout=timeout)
            self._owns_client = True

    async def close(self) -> None:
        """Закриття HTTP-клієнта та звільнення пулу з'єднань."""
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        telegram_id: int | None = None,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Універсальний метод відправки HTTP-запитів до бекенду з обробкою статусів.

        Формує сервісні заголовки авторизації X-Internal-Token та ідентифікатор користувача X-Telegram-Id.
        Транслює HTTP-помилки у типізовані доменні винятки бота.
        """
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers: dict[str, str] = {
            "X-Internal-Token": self._internal_token,
        }
        if telegram_id is not None:
            headers["X-Telegram-Id"] = str(telegram_id)

        try:
            response = await self._client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
            )
        except httpx.HTTPError as exc:
            logger.error(
                "Мережева помилка з'єднання з бекендом: {method} {url} -> {error}",
                method=method,
                url=url,
                error=str(exc),
            )
            raise BotApiError(
                status_code=503,
                message=f"Мережева помилка підключення до бекенду: {exc}",
            ) from exc

        if response.is_error:
            status_code = response.status_code
            error_details: dict[str, Any] = {}
            error_message = f"Помилка виклику API бекенду [{status_code}]."

            try:
                data = response.json()
                if isinstance(data, dict):
                    error_details = data
                    raw_msg = data.get("detail", data.get("message", error_message))
                    error_message = raw_msg if isinstance(raw_msg, str) else str(raw_msg)
            except Exception:
                if response.text:
                    error_message = response.text

            logger.warning(
                "Помилка відповіді бекенду: {method} {url} [{status_code}] {message}",
                method=method,
                url=url,
                status_code=status_code,
                message=error_message,
            )

            if status_code == 404:
                raise BotApiNotFoundError(message=error_message, details=error_details)
            if status_code == 409:
                raise BotApiConflictError(message=error_message, details=error_details)
            if status_code in (400, 422):
                raise BotApiValidationError(status_code=status_code, message=error_message, details=error_details)

            raise BotApiError(status_code=status_code, message=error_message, details=error_details)

        if response.status_code == 204:
            return None

        return response.json()

    # =========================================================================
    # Методи взаємодії з модулем Users
    # =========================================================================

    async def sync_telegram_user(
        self,
        cmd: RegisterTelegramUserCommand,
    ) -> UserResponseDTO:
        """Синхронізація облікового запису користувача Telegram у системі."""
        data = await self._request(
            "POST",
            "/users/telegram/sync",
            json_data=cmd.model_dump(mode="json"),
        )
        return UserResponseDTO.model_validate(data)

    async def get_my_profile(self, telegram_id: int) -> UserResponseDTO:
        """Отримання профілю поточного користувача за його Telegram ID."""
        data = await self._request(
            "GET",
            "/users/me",
            telegram_id=telegram_id,
        )
        return UserResponseDTO.model_validate(data)

    async def get_user_settings(self, telegram_id: int) -> UserSettingsResponseDTO:
        """Отримання налаштувань поточного користувача."""
        data = await self._request(
            "GET",
            "/users/me/settings",
            telegram_id=telegram_id,
        )
        return UserSettingsResponseDTO.model_validate(data)

    async def update_user_settings(
        self,
        telegram_id: int,
        cmd: UpdateUserSettingsCommand,
    ) -> UserSettingsResponseDTO:
        """Точкове оновлення налаштувань користувача з контролем версій (OCC)."""
        data = await self._request(
            "PATCH",
            "/users/me/settings",
            telegram_id=telegram_id,
            json_data=cmd.model_dump(mode="json", exclude_unset=True),
        )
        return UserSettingsResponseDTO.model_validate(data)

    # =========================================================================
    # Методи взаємодії з модулем Reminders
    # =========================================================================

    async def create_reminder(
        self,
        telegram_id: int,
        cmd: CreateReminderCommand,
    ) -> ReminderResponseDTO:
        """Створення нового нагадування будь-якого з 5 підтримуваних типів."""
        data = await self._request(
            "POST",
            "/reminders",
            telegram_id=telegram_id,
            json_data=cmd.model_dump(mode="json"),
        )
        return ReminderResponseDTO.model_validate(data)

    async def list_reminders(
        self,
        telegram_id: int,
        *,
        page: int = 1,
        size: int = 5,
        reminder_type: ReminderType | None = None,
        status: ReminderStatus | None = None,
    ) -> PaginatedResponse[ReminderResponseDTO]:
        """Отримання пагінованого списку нагадувань користувача з опціональною фільтрацією."""
        params: dict[str, Any] = {"page": page, "size": size}
        if reminder_type is not None:
            params["reminder_type"] = reminder_type.value if hasattr(reminder_type, "value") else str(reminder_type)
        if status is not None:
            params["status"] = status.value if hasattr(status, "value") else str(status)

        data = await self._request(
            "GET",
            "/reminders",
            telegram_id=telegram_id,
            params=params,
        )
        return PaginatedResponse[ReminderResponseDTO].model_validate(data)

    async def get_reminder(
        self,
        telegram_id: int,
        reminder_id: UUID,
    ) -> ReminderResponseDTO:
        """Отримання детальної інформації про нагадування за його UUIDv7."""
        data = await self._request(
            "GET",
            f"/reminders/{reminder_id}",
            telegram_id=telegram_id,
        )
        return ReminderResponseDTO.model_validate(data)

    async def patch_reminder(
        self,
        telegram_id: int,
        reminder_id: UUID,
        cmd: PatchReminderCommand,
    ) -> ReminderResponseDTO:
        """Часткове оновлення окремих полів нагадування з контролем версій (OCC)."""
        data = await self._request(
            "PATCH",
            f"/reminders/{reminder_id}",
            telegram_id=telegram_id,
            json_data=cmd.model_dump(mode="json", exclude_unset=True),
        )
        return ReminderResponseDTO.model_validate(data)

    async def perform_reminder_action(
        self,
        telegram_id: int,
        reminder_id: UUID,
        cmd: ReminderActionCommand,
    ) -> ReminderResponseDTO:
        """Виконання інтерактивної дії користувача над нагадуванням (RPC action)."""
        data = await self._request(
            "POST",
            f"/reminders/{reminder_id}/actions",
            telegram_id=telegram_id,
            json_data=cmd.model_dump(mode="json"),
        )
        return ReminderResponseDTO.model_validate(data)

    async def get_medication_logs(
        self,
        telegram_id: int,
        reminder_id: UUID,
    ) -> MedicationAdherenceStatsDTO:
        """Отримання журналу прийому та статистики комплаєнсу медикаменту."""
        data = await self._request(
            "GET",
            f"/reminders/{reminder_id}/medication-logs",
            telegram_id=telegram_id,
        )
        return MedicationAdherenceStatsDTO.model_validate(data)

    async def delete_reminder(
        self,
        telegram_id: int,
        reminder_id: UUID,
        *,
        hard: bool = False,
    ) -> None:
        """Видалення нагадування користувача (м'яке або остаточне фізичне)."""
        await self._request(
            "DELETE",
            f"/reminders/{reminder_id}",
            telegram_id=telegram_id,
            params={"hard": "true" if hard else "false"},
        )

    # =========================================================================
    # Методи взаємодії з модулем Finance
    # =========================================================================

    async def get_latest_rates(self, telegram_id: int) -> list[ExchangeRateResponseDTO]:
        """Отримання актуальних курсів валют (НБУ, Monobank, ПриватБанк)."""
        data = await self._request(
            "GET",
            "/finance/rates/latest",
            telegram_id=telegram_id,
        )
        if isinstance(data, list):
            return [ExchangeRateResponseDTO.model_validate(item) for item in data]
        return []
