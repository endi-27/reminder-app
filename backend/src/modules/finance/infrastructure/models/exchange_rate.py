from decimal import Decimal

from sqlalchemy import Enum, Index, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.modules.finance.domain.enums import CurrencyCode, ExchangeRateProvider


class ExchangeRateModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    """
    ORM-модель історичного знімку курсу валют (Append-Only таблиця exchange_rates).

    Таблиця містить лише ідентифікатор UUIDv7 та дату фіксації created_at (UTC).
    Поля оновлення updated_at, м'якого видалення deleted_at та версії OCC відсутні.
    """

    __tablename__ = "exchange_rates"

    __table_args__ = (
        Index(
            "idx_exchange_rates_provider_currency_created",
            "provider",
            "target_currency",
            text("created_at DESC"),
        ),
    )

    provider: Mapped[ExchangeRateProvider] = mapped_column(
        Enum(
            ExchangeRateProvider,
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    base_currency: Mapped[CurrencyCode] = mapped_column(
        Enum(
            CurrencyCode,
            native_enum=False,
            create_constraint=False,
            length=3,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=CurrencyCode.UAH,
        server_default="UAH",
        nullable=False,
    )
    target_currency: Mapped[CurrencyCode] = mapped_column(
        Enum(
            CurrencyCode,
            native_enum=False,
            create_constraint=False,
            length=3,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    rate_buy: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )
    rate_sell: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )
