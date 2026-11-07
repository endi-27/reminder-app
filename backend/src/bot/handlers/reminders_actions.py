from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks.data import ReminderActionCallback
from src.bot.client.api_client import BackendApiClient
from src.bot.formatters.messages import format_action_confirmation
from src.modules.reminders.application.dto import ReminderActionCommand, ReminderActionType
from src.modules.reminders.domain.enums import MedicationLogStatus
from src.modules.users.queries.dto import UserResponseDTO

reminders_actions_router = Router(name="reminders_actions")


@reminders_actions_router.callback_query(ReminderActionCallback.filter())
async def handle_reminder_action_callback(
    callback: CallbackQuery,
    callback_data: ReminderActionCallback,
    current_user: UserResponseDTO,
    api_client: BackendApiClient,
) -> None:
    """
    Обробник інтерактивних кнопок дій безпосередньо під пуш-сповіщеннями.

    Підтримує фіксацію оплати, прийом/пропуск ліків, виконання, скасування та відкладення (snooze).
    Після виконання RPC-дії редагує повідомлення сповіщення, видаляючи інлайн-кнопки
    та відображаючи підтвердження результату дії.
    """
    telegram_id = (
        current_user.telegram_account.telegram_id
        if current_user.telegram_account
        else (callback.from_user.id if callback.from_user else 0)
    )
    user_tz = current_user.settings.timezone
    action = callback_data.action

    if action == "payment":
        cmd = ReminderActionCommand(action=ReminderActionType.RECORD_PAYMENT)
    elif action == "med_taken":
        cmd = ReminderActionCommand(
            action=ReminderActionType.RECORD_MEDICATION_INTAKE,
            medication_status=MedicationLogStatus.TAKEN,
        )
    elif action == "med_missed":
        cmd = ReminderActionCommand(
            action=ReminderActionType.RECORD_MEDICATION_INTAKE,
            medication_status=MedicationLogStatus.MISSED,
        )
    elif action == "complete":
        cmd = ReminderActionCommand(action=ReminderActionType.COMPLETE)
    elif action == "cancel":
        cmd = ReminderActionCommand(action=ReminderActionType.CANCEL)
    elif action == "snooze":
        snooze_min = max(1, callback_data.minutes) if callback_data.minutes else 15
        cmd = ReminderActionCommand(
            action=ReminderActionType.SNOOZE,
            snooze_minutes=snooze_min,
        )
    elif action == "pause":
        cmd = ReminderActionCommand(action=ReminderActionType.PAUSE)
    elif action == "resume":
        cmd = ReminderActionCommand(action=ReminderActionType.RESUME)
    else:
        cmd = ReminderActionCommand(action=ReminderActionType(action))

    updated = await api_client.perform_reminder_action(
        telegram_id,
        callback_data.reminder_id,
        cmd,
    )

    original_text = ""
    if isinstance(callback.message, Message):
        original_text = callback.message.text or callback.message.caption or ""

    new_text = format_action_confirmation(
        original_text=original_text,
        action=action,
        updated=updated,
        minutes=callback_data.minutes,
        user_timezone=user_tz,
    )

    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(new_text, reply_markup=None)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise

    await callback.answer("✅ Дію виконано!")
