from decimal import Decimal

from sqlalchemy import Enum, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.modules.finance.domain.enums import ExchangeRateProvider


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
            name="exchange_rate_provider_enum",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=True,
        ),
        nullable=False,
    )
    base_currency: Mapped[str] = mapped_column(
        String(3),
        default="UAH",
        server_default="UAH",
        nullable=False,
    )
    target_currency: Mapped[str] = mapped_column(
        String(3),
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
