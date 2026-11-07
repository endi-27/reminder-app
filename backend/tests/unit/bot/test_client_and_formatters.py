import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from uuid6 import uuid7

from src.api.schemas.pagination import PaginatedResponse
from src.bot.callbacks import (
    CreateReminderTypeCallback,
    CreateWizardCallback,
    ReminderActionCallback,
    ReminderDetailCallback,
    ReminderListFilterCallback,
    SettingsCallback,
)
from src.bot.client import (
    BackendApiClient,
    BotApiConflictError,
    BotApiError,
    BotApiNotFoundError,
    BotApiValidationError,
)
from src.bot.formatters import (
    format_action_confirmation,
    format_help_message,
    format_medication_stats_message,
    format_notification_payload,
    format_rates_message,
    format_reminder_detail_message,
    format_reminders_list_message,
    format_settings_message,
    format_welcome_message,
)
from src.bot.states import (
    AnniversaryCreateStates,
    DeadlineTaskCreateStates,
    MedicationCreateStates,
    OpenTaskCreateStates,
    SettingsEditStates,
    SubscriptionCreateStates,
)
from src.infrastructure.notifications.dto import (
    DigestTaskItemDTO,
    NotificationEventType,
    NotificationPayload,
)
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.queries.dto import ExchangeRateResponseDTO
from src.modules.reminders.application.dto import (
    CreateReminderCommand,
    PatchReminderCommand,
    ReminderActionCommand,
    ReminderActionType,
)
from src.modules.reminders.domain.enums import (
    CurrencyCode,
    MedicationLogStatus,
    Priority,
    ReminderStatus,
    ReminderType,
    ScheduleLogicType,
)
from src.modules.reminders.queries.dto import (
    MedicationAdherenceStatsDTO,
    MedicationIntakeLogResponseDTO,
    ReminderResponseDTO,
)
from src.modules.users.application.dto import (
    RegisterTelegramUserCommand,
    UpdateUserSettingsCommand,
)
from src.modules.users.domain.enums import (
    ExchangeRateProvider as UserExchangeRateProvider,
)
from src.modules.users.domain.enums import (
    UserRole,
)
from src.modules.users.queries.dto import (
    TelegramAccountResponseDTO,
    UserResponseDTO,
    UserSettingsResponseDTO,
)


def _make_dummy_user_dto(user_id: UUID, tg_id: int = 123456789) -> UserResponseDTO:
    return UserResponseDTO(
        id=user_id,
        username="test_username",
        role=UserRole.USER,
        telegram_account=TelegramAccountResponseDTO(
            id=uuid7(),
            telegram_id=tg_id,
            telegram_chat_id=tg_id,
            tg_username="tg_alias",
            tg_full_name="Олександр Шевченко",
            version=1,
        ),
        settings=UserSettingsResponseDTO(
            id=uuid7(),
            user_id=user_id,
            timezone="Europe/Kyiv",
            quiet_hours_start=time(23, 0),
            quiet_hours_end=time(8, 0),
            preferred_bank=UserExchangeRateProvider.MONOBANK,
            auto_deadline_priority_escalation=True,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_dummy_reminder_dto(
    reminder_id: UUID,
    user_id: UUID,
    reminder_type: ReminderType = ReminderType.OPEN_TASK,
    status: ReminderStatus = ReminderStatus.ACTIVE,
) -> ReminderResponseDTO:
    return ReminderResponseDTO(
        id=reminder_id,
        user_id=user_id,
        reminder_type=reminder_type,
        schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
        title="Зробити зарядку",
        description="15 хвилин розминки вранці",
        status=status,
        next_trigger_at=datetime(2026, 11, 8, 7, 0, tzinfo=UTC),
        schedule_config={"times": ["07:00:00"]},
        lead_times=[],
        created_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        version=1,
    )


# =============================================================================
# 1. Тести BackendApiClient через httpx.MockTransport
# =============================================================================


class TestBackendApiClient:
    """Тести HTTP-клієнта BackendApiClient для зв'язку з бекендом."""

    @pytest.mark.asyncio
    async def test_sync_telegram_user_success(self) -> None:
        user_id = uuid7()
        user_dto = _make_dummy_user_dto(user_id)

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/api/v1/users/telegram/sync"
            assert request.headers["X-Internal-Token"] == "secret-test-token"
            body = json.loads(request.content)
            assert body["telegram_id"] == 123456789
            return httpx.Response(200, json=user_dto.model_dump(mode="json"))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-test-token",
                http_client=http_client,
            )
            cmd = RegisterTelegramUserCommand(
                telegram_id=123456789,
                telegram_chat_id=123456789,
                tg_username="tg_alias",
                tg_full_name="Олександр Шевченко",
            )
            result = await client.sync_telegram_user(cmd)
            assert result.id == user_id
            assert result.username == "test_username"

    @pytest.mark.asyncio
    async def test_get_my_profile_success(self) -> None:
        user_id = uuid7()
        user_dto = _make_dummy_user_dto(user_id)

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/v1/users/me"
            assert request.headers["X-Telegram-Id"] == "123456789"
            return httpx.Response(200, json=user_dto.model_dump(mode="json"))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            result = await client.get_my_profile(telegram_id=123456789)
            assert result.id == user_id

    @pytest.mark.asyncio
    async def test_get_and_update_user_settings(self) -> None:
        user_id = uuid7()
        user_dto = _make_dummy_user_dto(user_id)
        settings_dto = user_dto.settings

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Telegram-Id"] == "123456789"
            if request.method == "GET":
                assert request.url.path == "/api/v1/users/me/settings"
                return httpx.Response(200, json=settings_dto.model_dump(mode="json"))
            if request.method == "PATCH":
                assert request.url.path == "/api/v1/users/me/settings"
                data = json.loads(request.content)
                assert data["version"] == 1
                assert data["preferred_bank"] == "PRIVATBANK"
                updated_dto = settings_dto.model_copy(
                    update={"preferred_bank": UserExchangeRateProvider.PRIVATBANK, "version": 2}
                )
                return httpx.Response(200, json=updated_dto.model_dump(mode="json"))
            return httpx.Response(405)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            cur = await client.get_user_settings(123456789)
            assert cur.preferred_bank == UserExchangeRateProvider.MONOBANK

            cmd = UpdateUserSettingsCommand(
                version=1,
                preferred_bank=UserExchangeRateProvider.PRIVATBANK,
            )
            updated = await client.update_user_settings(123456789, cmd)
            assert updated.preferred_bank == UserExchangeRateProvider.PRIVATBANK
            assert updated.version == 2

    @pytest.mark.asyncio
    async def test_create_and_get_reminder(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()
        rem_dto = _make_dummy_reminder_dto(rem_id, user_id)

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Telegram-Id"] == "987654321"
            if request.method == "POST":
                assert request.url.path == "/api/v1/reminders"
                return httpx.Response(201, json=rem_dto.model_dump(mode="json"))
            if request.method == "GET":
                assert request.url.path == f"/api/v1/reminders/{rem_id}"
                return httpx.Response(200, json=rem_dto.model_dump(mode="json"))
            return httpx.Response(405)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            cmd = CreateReminderCommand(
                reminder_type=ReminderType.OPEN_TASK,
                schedule_logic=ScheduleLogicType.DAILY_AT_TIMES,
                title="Зробити зарядку",
                schedule_config={"times": ["07:00:00"]},
            )
            created = await client.create_reminder(987654321, cmd)
            assert created.id == rem_id

            fetched = await client.get_reminder(987654321, rem_id)
            assert fetched.id == rem_id

    @pytest.mark.asyncio
    async def test_list_reminders_with_filters(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()
        rem_dto = _make_dummy_reminder_dto(rem_id, user_id)
        paginated_response = PaginatedResponse[ReminderResponseDTO](
            items=[rem_dto],
            total=1,
            page=1,
            size=5,
            pages=1,
        )

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/v1/reminders"
            assert request.url.params["page"] == "1"
            assert request.url.params["size"] == "5"
            assert request.url.params["reminder_type"] == "OPEN_TASK"
            assert request.url.params["status"] == "ACTIVE"
            return httpx.Response(200, json=paginated_response.model_dump(mode="json"))

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            res = await client.list_reminders(
                123456789,
                page=1,
                size=5,
                reminder_type=ReminderType.OPEN_TASK,
                status=ReminderStatus.ACTIVE,
            )
            assert res.total == 1
            assert len(res.items) == 1
            assert res.items[0].id == rem_id

    @pytest.mark.asyncio
    async def test_patch_and_action_and_delete_reminder(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()
        rem_dto = _make_dummy_reminder_dto(rem_id, user_id)

        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Telegram-Id"] == "123456789"
            if request.method == "PATCH" and request.url.path == f"/api/v1/reminders/{rem_id}":
                data = json.loads(request.content)
                assert data["title"] == "Оновлена зарядка"
                return httpx.Response(
                    200,
                    json=rem_dto.model_copy(update={"title": "Оновлена зарядка"}).model_dump(mode="json"),
                )
            if request.method == "POST" and request.url.path == f"/api/v1/reminders/{rem_id}/actions":
                data = json.loads(request.content)
                assert data["action"] == "COMPLETE"
                return httpx.Response(
                    200,
                    json=rem_dto.model_copy(update={"status": ReminderStatus.COMPLETED}).model_dump(mode="json"),
                )
            if request.method == "DELETE" and request.url.path == f"/api/v1/reminders/{rem_id}":
                assert request.url.params["hard"] == "false"
                return httpx.Response(204)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            patched = await client.patch_reminder(
                123456789,
                rem_id,
                PatchReminderCommand(version=1, title="Оновлена зарядка"),
            )
            assert patched.title == "Оновлена зарядка"

            action_res = await client.perform_reminder_action(
                123456789,
                rem_id,
                ReminderActionCommand(action=ReminderActionType.COMPLETE),
            )
            assert action_res.status == ReminderStatus.COMPLETED

            await client.delete_reminder(123456789, rem_id, hard=False)

    @pytest.mark.asyncio
    async def test_get_medication_logs_and_latest_rates(self) -> None:
        rem_id = uuid7()
        stats_dto = MedicationAdherenceStatsDTO(
            reminder_id=rem_id,
            total_logs=5,
            taken_count=4,
            snoozed_count=1,
            missed_count=0,
            adherence_rate_percent=80.0,
            logs=[
                MedicationIntakeLogResponseDTO(
                    id=uuid7(),
                    reminder_id=rem_id,
                    scheduled_at=datetime(2026, 11, 7, 8, 0, tzinfo=UTC),
                    recorded_at=datetime(2026, 11, 7, 8, 5, tzinfo=UTC),
                    status=MedicationLogStatus.TAKEN,
                    created_at=datetime(2026, 11, 7, 8, 5, tzinfo=UTC),
                    version=1,
                )
            ],
        )

        rate_dto = ExchangeRateResponseDTO(
            id=uuid7(),
            provider=ExchangeRateProvider.MONOBANK,
            base_currency="UAH",
            target_currency="USD",
            rate_buy=Decimal("41.20"),
            rate_sell=Decimal("41.75"),
            created_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        )

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == f"/api/v1/reminders/{rem_id}/medication-logs":
                return httpx.Response(200, json=stats_dto.model_dump(mode="json"))
            if request.url.path == "/api/v1/finance/rates/latest":
                return httpx.Response(200, json=[rate_dto.model_dump(mode="json")])
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            logs = await client.get_medication_logs(123456789, rem_id)
            assert logs.adherence_rate_percent == 80.0

            rates = await client.get_latest_rates(123456789)
            assert len(rates) == 1
            assert rates[0].target_currency == "USD"
            assert rates[0].rate_buy == Decimal("41.20")

    @pytest.mark.asyncio
    async def test_error_mappings_404_409_422_500(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "not-found" in path:
                return httpx.Response(404, json={"detail": "Ресурс не знайдено."})
            if "conflict" in path:
                return httpx.Response(409, json={"detail": "Конфлікт версії OCC."})
            if "validation" in path:
                return httpx.Response(422, json={"detail": "Некоректне значення поля."})
            return httpx.Response(500, json={"detail": "Внутрішня помилка сервера."})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )

            with pytest.raises(BotApiNotFoundError) as exc_404:
                await client._request("GET", "/not-found")
            assert exc_404.value.status_code == 404
            assert "Ресурс не знайдено" in exc_404.value.message

            with pytest.raises(BotApiConflictError) as exc_409:
                await client._request("POST", "/conflict")
            assert exc_409.value.status_code == 409
            assert "Конфлікт версії OCC" in exc_409.value.message

            with pytest.raises(BotApiValidationError) as exc_422:
                await client._request("POST", "/validation")
            assert exc_422.value.status_code == 422

            with pytest.raises(BotApiError) as exc_500:
                await client._request("GET", "/server-error")
            assert exc_500.value.status_code == 500

    @pytest.mark.asyncio
    async def test_network_connection_error_raises_bot_api_error_503(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = BackendApiClient(
                base_url="http://testserver/api/v1",
                internal_token="secret-token",
                http_client=http_client,
            )
            with pytest.raises(BotApiError) as exc:
                await client.get_my_profile(111)
            assert exc.value.status_code == 503
            assert "Мережева помилка підключення" in exc.value.message


# =============================================================================
# 2. Тести CallbackData (pack/unpack та ліміт 64 байти)
# =============================================================================


class TestBotCallbacks:
    """Тести фабрик CallbackData aiogram 3.x."""

    def test_reminder_action_callback_pack_unpack_and_size_limit(self) -> None:
        rem_id = uuid7()
        cb = ReminderActionCallback(action="snooze", reminder_id=rem_id, minutes=1440)
        packed = cb.pack()
        assert len(packed.encode("utf-8")) <= 64

        unpacked = ReminderActionCallback.unpack(packed)
        assert unpacked.action == "snooze"
        assert unpacked.reminder_id == rem_id
        assert unpacked.minutes == 1440

    def test_reminder_action_callback_unpack_manual_worker_string(self) -> None:
        rem_id = uuid7()
        raw_str = f"reminder:payment:{rem_id}:0"
        assert len(raw_str.encode("utf-8")) <= 64

        unpacked = ReminderActionCallback.unpack(raw_str)
        assert unpacked.action == "payment"
        assert unpacked.reminder_id == rem_id
        assert unpacked.minutes == 0

    def test_all_callback_factories_within_64_bytes(self) -> None:
        rem_id = uuid7()

        cb_list = ReminderListFilterCallback(category="DEADLINE_TASK", page=99)
        assert len(cb_list.pack().encode("utf-8")) <= 64
        assert ReminderListFilterCallback.unpack(cb_list.pack()).category == "DEADLINE_TASK"

        cb_det = ReminderDetailCallback(action="delete", reminder_id=rem_id)
        assert len(cb_det.pack().encode("utf-8")) <= 64
        assert ReminderDetailCallback.unpack(cb_det.pack()).action == "delete"

        cb_new = CreateReminderTypeCallback(reminder_type="SUBSCRIPTION")
        assert len(cb_new.pack().encode("utf-8")) <= 64
        assert ReminderDetailCallback is not None

        cb_wiz = CreateWizardCallback(step="duration", value="30")
        assert len(cb_wiz.pack().encode("utf-8")) <= 64
        assert CreateWizardCallback.unpack(cb_wiz.pack()).value == "30"

        cb_cfg = SettingsCallback(section="bank", value="MONOBANK")
        assert len(cb_cfg.pack().encode("utf-8")) <= 64
        assert SettingsCallback.unpack(cb_cfg.pack()).value == "MONOBANK"


# =============================================================================
# 3. Тести FSM StatesGroup
# =============================================================================


class TestFsmStates:
    """Тести груп станів діалогів створення та редагування."""

    def test_all_fsm_states_declared(self) -> None:
        assert hasattr(OpenTaskCreateStates, "waiting_for_title")
        assert hasattr(OpenTaskCreateStates, "waiting_for_times")

        assert hasattr(AnniversaryCreateStates, "waiting_for_title")
        assert hasattr(AnniversaryCreateStates, "waiting_for_date")
        assert hasattr(AnniversaryCreateStates, "waiting_for_lead_times")

        assert hasattr(DeadlineTaskCreateStates, "waiting_for_title")
        assert hasattr(DeadlineTaskCreateStates, "waiting_for_deadline")
        assert hasattr(DeadlineTaskCreateStates, "waiting_for_priority")

        assert hasattr(SubscriptionCreateStates, "waiting_for_title")
        assert hasattr(SubscriptionCreateStates, "waiting_for_amount_currency")
        assert hasattr(SubscriptionCreateStates, "waiting_for_billing_day")
        assert hasattr(SubscriptionCreateStates, "waiting_for_mode")
        assert hasattr(SubscriptionCreateStates, "waiting_for_trial_date")
        assert hasattr(SubscriptionCreateStates, "waiting_for_discount_details")

        assert hasattr(MedicationCreateStates, "waiting_for_title")
        assert hasattr(MedicationCreateStates, "waiting_for_schedule_mode")
        assert hasattr(MedicationCreateStates, "waiting_for_schedule_value")
        assert hasattr(MedicationCreateStates, "waiting_for_duration")
        assert hasattr(MedicationCreateStates, "waiting_for_strict_mode")

        assert hasattr(SettingsEditStates, "waiting_for_custom_quiet_hours")
        assert hasattr(SettingsEditStates, "waiting_for_custom_timezone")


# =============================================================================
# 4. Тести HTML форматувальників (messages.py)
# =============================================================================


class TestMessageFormatters:
    """Тести чистого форматування HTML-повідомлень українською мовою."""

    def test_format_welcome_message_escapes_xss(self) -> None:
        user_id = uuid7()
        user_dto = _make_dummy_user_dto(user_id)
        assert user_dto.telegram_account is not None
        user_dto.telegram_account.tg_full_name = "<script>alert('xss')</script>"

        msg = format_welcome_message(user_dto)
        assert "<script>" not in msg
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in msg
        assert "Вітаємо у Reminder App" in msg

    def test_format_help_message_contains_commands(self) -> None:
        msg = format_help_message()
        assert "/start" in msg
        assert "/new" in msg
        assert "/list" in msg
        assert "/rates" in msg
        assert "/settings" in msg
        assert "/cancel" in msg
        assert "/help" in msg

    def test_format_settings_message(self) -> None:
        user_id = uuid7()
        user_dto = _make_dummy_user_dto(user_id)
        msg = format_settings_message(user_dto.settings)
        assert "Europe/Kyiv" in msg
        assert "23:00 – 08:00" in msg
        assert "Monobank (Монобанк)" in msg
        assert "Увімкнено ✅" in msg

    def test_format_rates_message_empty_and_populated(self) -> None:
        assert "Дані щодо курсів валют тимчасово недоступні" in format_rates_message([], "MONOBANK")

        rates = [
            ExchangeRateResponseDTO(
                id=uuid7(),
                provider=ExchangeRateProvider.MONOBANK,
                base_currency="UAH",
                target_currency="USD",
                rate_buy=Decimal("41.20"),
                rate_sell=Decimal("41.75"),
                created_at=datetime.now(UTC),
            ),
            ExchangeRateResponseDTO(
                id=uuid7(),
                provider=ExchangeRateProvider.NBU,
                base_currency="UAH",
                target_currency="EUR",
                rate_buy=None,
                rate_sell=Decimal("44.85"),
                created_at=datetime.now(UTC),
            ),
        ]
        msg = format_rates_message(rates, preferred_bank="MONOBANK")
        assert "Monobank ⭐ (Пріоритетний)" in msg
        assert "41.20" in msg
        assert "41.75" in msg
        assert "44.85" in msg

    def test_format_reminders_list_message(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()
        rem_dto = _make_dummy_reminder_dto(rem_id, user_id)
        rem_dto.title = "<b>Тестове нагадування</b>"

        empty_page = PaginatedResponse[ReminderResponseDTO](items=[], total=0, page=1, size=5, pages=0)
        empty_msg = format_reminders_list_message(empty_page, "ALL", "Europe/Kyiv")
        assert "У цій категорії наразі немає створених нагадувань" in empty_msg

        populated_page = PaginatedResponse[ReminderResponseDTO](items=[rem_dto], total=1, page=1, size=5, pages=1)
        pop_msg = format_reminders_list_message(populated_page, "OPEN_TASK", "Europe/Kyiv")
        assert "&lt;b&gt;Тестове нагадування&lt;/b&gt;" in pop_msg
        assert "📝" in pop_msg
        assert "🟢 Активне" in pop_msg
        assert "Сторінка 1 з 1" in pop_msg

    def test_format_reminder_detail_message_all_types(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()

        # Тест нагадування про ліки зі суворим графіком
        med_dto = ReminderResponseDTO(
            id=rem_id,
            user_id=user_id,
            reminder_type=ReminderType.MEDICATION,
            schedule_logic=ScheduleLogicType.INTERVAL_HOURS,
            title="Амоксиклав 1000",
            description="Після їжі",
            status=ReminderStatus.ACTIVE,
            next_trigger_at=datetime(2026, 11, 8, 8, 0, tzinfo=UTC),
            schedule_config={"interval_hours": 8},
            lead_times=[],
            course_duration_days=7,
            medication_start_date=date(2026, 11, 1),
            medication_end_date=date(2026, 11, 8),
            strict_schedule=True,
            created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            version=1,
        )
        med_msg = format_reminder_detail_message(med_dto, "Europe/Kyiv")
        assert "💊" in med_msg
        assert "Амоксиклав 1000" in med_msg
        assert "Тривалість курсу:</b> 7 днів" in med_msg
        assert "🚨 Суворий (будити навіть уночі)" in med_msg

        # Тест підписки з акційною знижкою
        sub_dto = ReminderResponseDTO(
            id=rem_id,
            user_id=user_id,
            reminder_type=ReminderType.SUBSCRIPTION,
            schedule_logic=ScheduleLogicType.DATE_WITH_MONTH_INTERVAL,
            title="Spotify Premium",
            status=ReminderStatus.ACTIVE,
            next_trigger_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
            schedule_config={"day": 15, "interval_months": 1},
            lead_times=["3d", "1d"],
            regular_amount=Decimal("4.99"),
            currency="USD",
            discount_amount=Decimal("2.49"),
            discount_cycles_total=3,
            discount_cycles_remaining=2,
            created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            version=2,
        )
        sub_msg = format_reminder_detail_message(sub_dto, "Europe/Kyiv")
        assert "💳" in sub_msg
        assert "4.99 USD" in sub_msg
        assert "2.49 USD" in sub_msg
        assert "залишилось 2 з 3 циклів" in sub_msg

        # Тест дедлайну
        deadline_dto = ReminderResponseDTO(
            id=rem_id,
            user_id=user_id,
            reminder_type=ReminderType.DEADLINE_TASK,
            schedule_logic=ScheduleLogicType.EXACT_DATETIME_DEADLINE,
            title="Подати звіт до податкової",
            status=ReminderStatus.ACTIVE,
            next_trigger_at=datetime(2026, 11, 10, 18, 0, tzinfo=UTC),
            due_datetime=datetime(2026, 11, 10, 18, 0, tzinfo=UTC),
            base_priority=Priority.HIGH,
            calculated_priority=Priority.CRITICAL,
            schedule_config={"due_datetime": "2026-11-10T18:00:00Z"},
            lead_times=["1d", "3h"],
            created_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
            version=1,
        )
        dead_msg = format_reminder_detail_message(deadline_dto, "Europe/Kyiv")
        assert "🔥" in dead_msg
        assert "🔴 Критичний" in dead_msg

    def test_format_medication_stats_message(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()
        rem_dto = _make_dummy_reminder_dto(rem_id, user_id, ReminderType.MEDICATION)
        stats_dto = MedicationAdherenceStatsDTO(
            reminder_id=rem_id,
            total_logs=4,
            taken_count=3,
            snoozed_count=1,
            missed_count=0,
            adherence_rate_percent=75.0,
            logs=[
                MedicationIntakeLogResponseDTO(
                    id=uuid7(),
                    reminder_id=rem_id,
                    scheduled_at=datetime(2026, 11, 7, 8, 0, tzinfo=UTC),
                    recorded_at=datetime(2026, 11, 7, 8, 2, tzinfo=UTC),
                    status=MedicationLogStatus.TAKEN,
                    created_at=datetime(2026, 11, 7, 8, 2, tzinfo=UTC),
                    version=1,
                )
            ],
        )
        msg = format_medication_stats_message(rem_dto, stats_dto, "Europe/Kyiv")
        assert "75.0%" in msg
        assert "✅ Прийнято" in msg

    def test_format_action_confirmation(self) -> None:
        user_id = uuid7()
        rem_id = uuid7()
        rem_dto = _make_dummy_reminder_dto(rem_id, user_id)
        original = "💳 Нагадування про оплату підписки: Netflix"

        conf_pay = format_action_confirmation(original, "payment", rem_dto, 0, "Europe/Kyiv")
        assert "✅ <b>Оплату підписки зафіксовано!</b>" in conf_pay
        assert "<s>💳 Нагадування про оплату підписки: Netflix</s>" in conf_pay

        conf_snooze = format_action_confirmation(original, "snooze", rem_dto, 15, "Europe/Kyiv")
        assert "⏰ <b>Відкладено на 15 хв</b>" in conf_snooze

        conf_cancel = format_action_confirmation(original, "cancel", rem_dto, 0, "Europe/Kyiv")
        assert "❌ <b>Підписку успішно скасовано.</b>" in conf_cancel

    def test_format_notification_payload_daily_digest(self) -> None:
        empty_payload = NotificationPayload(
            event_type=NotificationEventType.DAILY_DIGEST,
            recipient_chat_id=123,
            digest_tasks=[],
        )
        empty_text = format_notification_payload(empty_payload)
        assert "📋 <b>Ваш щоденний дайджест відкритих справ:</b>" in empty_text
        assert "<i>На сьогодні немає відкритих справ.</i>" in empty_text

        tasks_payload = NotificationPayload(
            event_type=NotificationEventType.DAILY_DIGEST,
            recipient_chat_id=123,
            digest_tasks=[
                DigestTaskItemDTO(
                    reminder_id=uuid7(),
                    title="Купити каву & круасан",
                    description="В улюбленій кав'ярні",
                    priority=Priority.HIGH,
                ),
                DigestTaskItemDTO(
                    reminder_id=uuid7(),
                    title="Зателефонувати <колезі>",
                    description=None,
                    priority=None,
                ),
            ],
        )
        tasks_text = format_notification_payload(tasks_payload)
        assert "📋 <b>Ваш щоденний дайджест відкритих справ:</b>" in tasks_text
        assert "• [ВИСОКИЙ] <b>Купити каву &amp; круасан</b>" in tasks_text
        assert "  В улюбленій кав&#x27;ярні" in tasks_text
        assert "• <b>Зателефонувати &lt;колезі&gt;</b>" in tasks_text

    def test_format_notification_payload_trial_expired(self) -> None:
        payload = NotificationPayload(
            event_type=NotificationEventType.TRIAL_EXPIRED,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.SUBSCRIPTION,
            title="YouTube <Premium>",
            amount=Decimal("99.99"),
            currency=CurrencyCode.UAH,
        )
        text = format_notification_payload(payload)
        assert "💳 <b>Пробний період підписки «YouTube &lt;Premium&gt;» завершився!</b>" in text
        assert "Підписку переведено у регулярний платний статус." in text
        assert "<code>99.99 UAH</code>." in text

    def test_format_notification_payload_subscription_due(self) -> None:
        # 1. Звичайна UAH без конвертації
        p_uah = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.SUBSCRIPTION,
            title="Оренда квартири",
            amount=Decimal("15000.00"),
            currency=CurrencyCode.UAH,
            description="Оплата власнику на карту",
        )
        text_uah = format_notification_payload(p_uah)
        assert "💳 <b>Нагадування про оплату підписки: Оренда квартири</b>" in text_uah
        assert "Сума до сплати: <code>15000.00 UAH</code>" in text_uah
        assert "Оплата власнику на карту" in text_uah

        # 2. Валютна з конвертацією та попередженням про застарілий курс
        p_usd = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.SUBSCRIPTION,
            title="Netflix <4K>",
            amount=Decimal("9.99"),
            currency=CurrencyCode.USD,
            converted_amount_uah=Decimal("415.50"),
            rate_provider="Monobank",
            is_stale_rate_fallback=True,
            is_trial=True,
        )
        text_usd = format_notification_payload(p_usd)
        assert "💳 <b>Нагадування про оплату підписки: Netflix &lt;4K&gt;</b>" in text_usd
        assert "Сума до сплати: <code>9.99 USD</code> (≈ <b>415.50 грн</b> за курсом Monobank)" in text_usd
        assert "⚠️ <i>Курс обраного банку застарілий, використано офіційний курс НБУ.</i>" in text_usd
        assert "⚠️ <b>Закінчується пробний період підписки!</b>" in text_usd

        # 3. Останній цикл акційної знижки
        p_disc = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.SUBSCRIPTION,
            title="Setapp",
            amount=Decimal("4.99"),
            currency=CurrencyCode.USD,
            is_last_discount_cycle=True,
        )
        text_disc = format_notification_payload(p_disc)
        assert "⚠️ <b>Це останній платіжний цикл за зниженою акційною ціною!</b>" in text_disc

    def test_format_notification_payload_medication_due(self) -> None:
        payload = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.MEDICATION,
            title="Вітамін D3 <5000>",
            description="Приймати під час сніданку",
            medication_end_date=date(2026, 12, 31),
        )
        text = format_notification_payload(payload)
        assert "💊 <b>Час прийому ліків: Вітамін D3 &lt;5000&gt;</b>" in text
        assert "Приймати під час сніданку" in text
        assert "Курс триває до: <code>31.12.2026</code>" in text

    def test_format_notification_payload_deadline_due(self) -> None:
        payload = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.DEADLINE_TASK,
            title="Здати квартальний звіт",
            description="Завантажити у кабінет",
            due_datetime=datetime(2026, 11, 10, 16, 0, tzinfo=UTC),
            user_timezone="Europe/Kyiv",
            effective_priority=Priority.CRITICAL,
        )
        text = format_notification_payload(payload)
        assert "🔥 <b>[КРИТИЧНО] Дедлайн задачі: Здати квартальний звіт</b>" in text
        assert "Термін виконання: <code>10.11.2026 18:00</code>" in text
        assert "Завантажити у кабінет" in text

        # Без розрахованого пріоритету -> [ЗВИЧАЙНИЙ]
        p_def = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.DEADLINE_TASK,
            title="Проста справа з дедлайном",
            effective_priority=None,
        )
        text_def = format_notification_payload(p_def)
        assert "🔥 <b>[ЗВИЧАЙНИЙ] Дедлайн задачі: Проста справа з дедлайном</b>" in text_def

    def test_format_notification_payload_anniversary_due(self) -> None:
        p_age = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.ANNIVERSARY,
            title="День народження Марії",
            calculated_age=30,
            description="Подарувати квіти",
        )
        text_age = format_notification_payload(p_age)
        assert "🎉 <b>Сьогодні святкова подія: День народження Марії (30 р.)!</b>" in text_age
        assert "Подарувати квіти" in text_age

        p_no_age = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.ANNIVERSARY,
            title="День заснування компанії",
            calculated_age=None,
        )
        text_no_age = format_notification_payload(p_no_age)
        assert "🎉 <b>Сьогодні святкова подія: День заснування компанії!</b>" in text_no_age

    def test_format_notification_payload_open_task_and_fallback(self) -> None:
        p_open = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=ReminderType.OPEN_TASK,
            title="Зателефонувати сантехніку",
            description="Узгодити час візиту",
        )
        text_open = format_notification_payload(p_open)
        assert "📋 <b>Нагадування про справу: Зателефонувати сантехніку</b>" in text_open
        assert "Узгодити час візиту" in text_open

        # Fallback
        p_unknown = NotificationPayload(
            event_type=NotificationEventType.REMINDER_DUE,
            recipient_chat_id=123,
            reminder_id=uuid7(),
            reminder_type=None,
            title="Невідомий тип",
            description="Опис",
        )
        text_unknown = format_notification_payload(p_unknown)
        assert "🔔 <b>Невідомий тип</b>" in text_unknown
        assert "Опис" in text_unknown
