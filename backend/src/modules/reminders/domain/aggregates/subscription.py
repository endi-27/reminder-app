from dataclasses import dataclass
from datetime import UTC, date, datetime

from src.core.exceptions import InvalidDiscountCycleError, ValidationException
from src.modules.reminders.domain.aggregates.base import BaseReminder
from src.modules.reminders.domain.enums import ReminderStatus, ReminderType, ScheduleLogicType
from src.modules.reminders.domain.value_objects import Money


@dataclass(kw_only=True)
class SubscriptionReminder(BaseReminder):
    """
    Доменний агрегат регулярної фінансової підписки.
    Підтримує пробні періоди (Trial), акційні знижки на N циклів та мультивалютність.
    """

    reminder_type: ReminderType = ReminderType.SUBSCRIPTION
    schedule_logic: ScheduleLogicType = ScheduleLogicType.DATE_WITH_MONTH_INTERVAL
    regular_amount: Money
    is_trial: bool = False
    trial_end_date: date | None = None
    discount_amount: Money | None = None
    discount_cycles_total: int | None = None
    discount_cycles_remaining: int | None = None

    def __post_init__(self) -> None:
        """Перевіряє інваріанти тріалу, акційної вартості та відповідності валют."""
        super().__post_init__()

        if self.is_trial:
            if self.trial_end_date is None:
                raise ValidationException(
                    "Для пробного періоду (is_trial=True) обов'язково вказати дату завершення trial_end_date."
                )
            if self.status == ReminderStatus.ACTIVE:
                self.status = ReminderStatus.TRIAL

        if self.discount_amount is not None:
            if self.discount_cycles_total is None or self.discount_cycles_total < 1:
                raise InvalidDiscountCycleError("Загальна кількість акційних циклів зі знижкою має бути щонайменше 1.")

            if self.discount_cycles_remaining is None or not (
                0 <= self.discount_cycles_remaining <= self.discount_cycles_total
            ):
                raise InvalidDiscountCycleError(
                    "Кількість залишкових циклів знижки має знаходитися у межах від 0 до discount_cycles_total."
                )

            if self.discount_amount.currency != self.regular_amount.currency:
                raise InvalidDiscountCycleError(
                    f"Валюта акційної ціни ({self.discount_amount.currency.value}) має збігатися "
                    f"із валютою регулярного платежу ({self.regular_amount.currency.value})."
                )

    @property
    def active_amount(self) -> Money:
        """
        Активна вартість поточного платіжного циклу:
        Якщо діє знижка (discount_cycles_remaining > 0) — повертає discount_amount,
        інакше стандартну суму regular_amount.
        """
        if (
            self.discount_amount is not None
            and self.discount_cycles_remaining is not None
            and self.discount_cycles_remaining > 0
        ):
            return self.discount_amount
        return self.regular_amount

    @property
    def is_last_discount_cycle(self) -> bool:
        """Показує, чи є поточний платіж останнім за зниженою акційною ціною."""
        return self.discount_cycles_remaining == 1

    def convert_trial_to_paid(
        self,
        reference_time: datetime,
        user_timezone: str = "Europe/Kyiv",
    ) -> None:
        """
        Переводить підписку з пробного періоду (TRIAL) у регулярну платну (ACTIVE)
        та перераховує наступний платіж за основним розкладом.
        """
        self.ensure_active("перевести тріал деактивованої підписки у платний статус")
        self.is_trial = False
        self.status = ReminderStatus.ACTIVE
        self.trial_end_date = None
        self.advance_schedule(reference_time, user_timezone)

    def record_payment(
        self,
        reference_time: datetime | None = None,
        user_timezone: str = "Europe/Kyiv",
    ) -> Money:
        """
        Фіксує здійснення оплати за черговий платіжний цикл:
        - Якщо підписка була у тріалі — переводить у платний режим.
        - Якщо діє знижка — списує один акційний цикл (discount_cycles_remaining -= 1).
        - Зсуває next_trigger_at на наступний платіжний період.
        - Повертає фактично списану суму (Money).
        """
        self.ensure_active("зафіксувати оплату деактивованої підписки")

        paid_amount = self.active_amount

        if self.is_trial:
            self.is_trial = False
            self.status = ReminderStatus.ACTIVE
            self.trial_end_date = None

        if self.discount_cycles_remaining is not None and self.discount_cycles_remaining > 0:
            self.discount_cycles_remaining -= 1

        ref_time = reference_time or datetime.now(UTC)
        self.advance_schedule(ref_time, user_timezone)
        return paid_amount
