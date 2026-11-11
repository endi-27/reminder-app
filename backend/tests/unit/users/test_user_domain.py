from datetime import time

import pytest
from uuid6 import uuid7

from src.core.domain.enums import SystemRole
from src.core.exceptions import InactiveEntityError
from src.modules.finance.public import ExchangeRateProvider
from src.modules.users.domain.exceptions import (
    InvalidTimezoneError,
    SuperAdminDeletionForbiddenError,
    TelegramAccountAlreadyLinkedError,
)
from src.modules.users.domain.models import User, UserSettings


def test_user_creation_default_settings() -> None:
    """Тест створення користувача з автоматичною ініціалізацією типових налаштувань."""
    user_id = uuid7()
    user = User(id=user_id, username="alice", role=SystemRole.USER)

    assert user.id == user_id
    assert user.username == "alice"
    assert user.role == SystemRole.USER
    assert user.is_active is True
    assert user.telegram_account is None

    # Перевірка типових налаштувань
    settings = user.current_settings
    assert settings.user_id == user_id
    assert settings.timezone == "Europe/Kyiv"
    assert settings.quiet_hours_start == time(23, 0)
    assert settings.quiet_hours_end == time(8, 0)
    assert settings.preferred_bank == ExchangeRateProvider.MONOBANK
    assert settings.auto_deadline_priority_escalation is True


def test_user_settings_timezone_validation() -> None:
    """Тест валідації часового поясу за базою IANA."""
    user_id = uuid7()

    # Валідний часовий пояс
    settings = UserSettings(id=uuid7(), user_id=user_id, timezone="America/New_York")
    assert settings.timezone == "America/New_York"

    # Невалідний часовий пояс
    with pytest.raises(InvalidTimezoneError, match="Недійсний ідентифікатор"):
        UserSettings(id=uuid7(), user_id=user_id, timezone="Mars/Phobos")

    # Порожній рядок
    with pytest.raises(InvalidTimezoneError, match="не може бути порожнім"):
        UserSettings(id=uuid7(), user_id=user_id, timezone="")


def test_user_link_and_update_telegram_account() -> None:
    """Тест первинної прив'язки та подальшого оновлення реквізитів Telegram-акаунта."""
    user = User(id=uuid7(), username="bob")

    # Первинна прив'язка
    account = user.link_or_update_telegram(
        telegram_id=123456789,
        telegram_chat_id=987654321,
        tg_username="bob_tg",
        tg_full_name="Bob Builder",
    )

    assert user.telegram_account is not None
    assert user.telegram_account.telegram_id == 123456789
    assert user.telegram_account.telegram_chat_id == 987654321
    assert user.telegram_account.tg_username == "bob_tg"
    assert user.telegram_account.tg_full_name == "Bob Builder"
    assert account == user.telegram_account

    # Оновлення нікнейму та чату для того самого telegram_id
    user.link_or_update_telegram(
        telegram_id=123456789,
        telegram_chat_id=555555555,
        tg_username="bob_new_username",
        tg_full_name="Robert Builder",
    )
    assert user.telegram_account.telegram_chat_id == 555555555
    assert user.telegram_account.tg_username == "bob_new_username"
    assert user.telegram_account.tg_full_name == "Robert Builder"

    # Спроба підключити інший telegram_id викликає доменну помилку
    with pytest.raises(TelegramAccountAlreadyLinkedError):
        user.link_or_update_telegram(
            telegram_id=999999999,
            telegram_chat_id=999999999,
        )


def test_user_update_settings() -> None:
    """Тест оновлення параметрів налаштувань через агрегат користувача."""
    user = User(id=uuid7(), username="charlie")

    updated_settings = user.update_settings(
        timezone="Europe/Warsaw",
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(7, 30),
        preferred_bank=ExchangeRateProvider.PRIVATBANK,
        auto_deadline_priority_escalation=False,
    )

    assert updated_settings.timezone == "Europe/Warsaw"
    assert updated_settings.quiet_hours_start == time(22, 0)
    assert updated_settings.quiet_hours_end == time(7, 30)
    assert updated_settings.preferred_bank == ExchangeRateProvider.PRIVATBANK
    assert updated_settings.auto_deadline_priority_escalation is False


def test_super_admin_soft_delete_protection() -> None:
    """Тест захисту облікового запису SuperAdmin від видалення."""
    admin_user = User(id=uuid7(), username="root", role=SystemRole.SUPER_ADMIN)

    with pytest.raises(SuperAdminDeletionForbiddenError, match="SuperAdmin не може бути видалений"):
        admin_user.soft_delete()

    assert admin_user.is_active is True
    assert admin_user.deleted_at is None


def test_regular_user_soft_delete_and_restore() -> None:
    """Тест деактивації та наступного відновлення звичайного користувача."""
    user = User(id=uuid7(), username="dave", role=SystemRole.USER)
    assert user.is_active is True

    # Деактивація
    user.soft_delete()
    assert user.is_active is False
    assert user.deleted_at is not None

    # Відновлення
    user.restore()
    assert user.is_active is True
    assert user.deleted_at is None


def test_inactive_user_mutation_prevention() -> None:
    """Тест блокування будь-яких мутацій деактивованого облікового запису."""
    user = User(id=uuid7(), username="eve", role=SystemRole.USER)
    user.soft_delete()

    # Спроба змінити пароль
    with pytest.raises(InactiveEntityError):
        user.change_password("new_hash")

    # Спроба змінити роль
    with pytest.raises(InactiveEntityError):
        user.change_role(SystemRole.ADMIN)

    # Спроба оновити налаштування
    with pytest.raises(InactiveEntityError):
        user.update_settings(timezone="UTC")

    # Спроба прив'язати Telegram
    with pytest.raises(InactiveEntityError):
        user.link_or_update_telegram(telegram_id=1, telegram_chat_id=1)
