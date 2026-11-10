from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.core.exceptions import ValidationException
from src.modules.reminders.domain.enums import CurrencyCode


@dataclass(frozen=True)
class Money:
    """Незмінний грошовий Value Object із захистом від float-похибок та точним квантуванням."""

    amount: Decimal
    currency: CurrencyCode = CurrencyCode.UAH

    def __post_init__(self) -> None:
        """Валідує невід'ємність суми та квантує значення до 0.01 за банківським правилом."""
        if not isinstance(self.amount, Decimal):
            try:
                dec_amount = Decimal(str(self.amount))
            except Exception as exc:
                raise ValidationException("Грошова сума має бути валідним числовим значенням.") from exc
        else:
            dec_amount = self.amount

        if dec_amount < Decimal("0.00"):
            raise ValidationException("Грошова сума не може бути від'ємною.")

        quantized = dec_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency.value}"
