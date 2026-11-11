from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.core.config import settings
from src.core.domain.enums import CurrencyCode
from src.core.redis import RedisClient
from src.infrastructure.notifications import (
    NotificationEventType,
    NotificationPayload,
    RedisQueuePublisher,
)
from src.modules.finance.domain.enums import ExchangeRateProvider
from src.modules.finance.domain.models import ExchangeRate
from src.modules.finance.infrastructure.repository import SqlAlchemyExchangeRateRepository
from src.modules.finance.queries.query_service import FinanceQueryService
from src.modules.reminders.domain.enums import ReminderType


@pytest.mark.asyncio
async def test_exchange_rates_append_only_and_get_latest(db_session: AsyncSession) -> None:
    """
    Перевірка збереження знімків курсів валют у режимі Append-Only
    та отримання найсвіжішого курсу за індексом idx_exchange_rates_provider_currency_created.
    """
    repo = SqlAlchemyExchangeRateRepository(session=db_session)
    now = datetime.now(UTC)

    # Зберігаємо старіший курс USD від Monobank (1 година тому)
    older_rate = ExchangeRate(
        id=uuid7(),
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.20"),
        rate_buy=Decimal("40.80"),
        created_at=now - timedelta(hours=1),
    )

    # Зберігаємо новіший курс USD від Monobank (5 хвилин тому)
    newer_rate = ExchangeRate(
        id=uuid7(),
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.50"),
        rate_buy=Decimal("41.00"),
        created_at=now - timedelta(minutes=5),
    )

    # Зберігаємо курс EUR від NBU
    nbu_eur = ExchangeRate(
        id=uuid7(),
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.EUR,
        rate_sell=Decimal("44.80"),
        created_at=now - timedelta(minutes=10),
    )

    await repo.append(older_rate)
    await repo.append(newer_rate)
    await repo.append(nbu_eur)
    await db_session.flush()

    # Перевірка отримання останнього актуального курсу Monobank USD
    latest_mono_usd = await repo.get_latest(
        provider=ExchangeRateProvider.MONOBANK,
        target_currency=CurrencyCode.USD,
    )
    assert latest_mono_usd is not None
    assert latest_mono_usd.id == newer_rate.id
    assert latest_mono_usd.rate_sell == Decimal("41.50")
    assert latest_mono_usd.rate_buy == Decimal("41.00")

    # Перевірка пакетного збереження append_many
    batch_rates = [
        ExchangeRate(
            id=uuid7(),
            provider=ExchangeRateProvider.PRIVATBANK,
            target_currency=CurrencyCode.USD,
            rate_sell=Decimal("41.45"),
            created_at=now,
        ),
        ExchangeRate(
            id=uuid7(),
            provider=ExchangeRateProvider.PRIVATBANK,
            target_currency=CurrencyCode.EUR,
            rate_sell=Decimal("44.90"),
            created_at=now,
        ),
    ]
    await repo.append_many(batch_rates)
    await db_session.flush()

    privat_usd = await repo.get_latest(
        provider=ExchangeRateProvider.PRIVATBANK,
        target_currency=CurrencyCode.USD,
    )
    assert privat_usd is not None
    assert privat_usd.rate_sell == Decimal("41.45")


@pytest.mark.asyncio
async def test_finance_query_service_distinct_on(db_session: AsyncSession) -> None:
    """
    Перевірка роботи Read-Side FinanceQueryService.get_latest_rates():
    PostgreSQL DISTINCT ON (provider, target_currency) повертає лише найсвіжіші записи.
    """
    repo = SqlAlchemyExchangeRateRepository(session=db_session)
    query_service = FinanceQueryService(session=db_session)
    now = datetime.now(UTC)

    # Додаємо декілька записів для однієї пари (NBU, USD)
    rate_1 = ExchangeRate(
        id=uuid7(),
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("40.00"),
        created_at=now - timedelta(days=1),
    )
    rate_2 = ExchangeRate(
        id=uuid7(),
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.USD,
        rate_sell=Decimal("41.00"),
        created_at=now,
    )
    rate_3 = ExchangeRate(
        id=uuid7(),
        provider=ExchangeRateProvider.NBU,
        target_currency=CurrencyCode.EUR,
        rate_sell=Decimal("44.50"),
        created_at=now,
    )

    await repo.append_many([rate_1, rate_2, rate_3])
    await db_session.flush()

    latest_rates = await query_service.get_latest_rates()
    rates_map = {(r.provider, r.target_currency): r for r in latest_rates}

    assert (ExchangeRateProvider.NBU, CurrencyCode.USD) in rates_map
    nbu_usd_dto = rates_map[(ExchangeRateProvider.NBU, CurrencyCode.USD)]
    assert nbu_usd_dto.rate_sell == Decimal("41.00")
    assert nbu_usd_dto.id == rate_2.id

    assert (ExchangeRateProvider.NBU, CurrencyCode.EUR) in rates_map


@pytest.mark.asyncio
async def test_redis_queue_publisher_publish_and_brpop(redis_client: RedisClient) -> None:
    """
    Перевірка публікації повідомлень у чергу Redis (LPUSH)
    та їх вичитування консьюмером бота через блокуючий BRPOP.
    """
    publisher = RedisQueuePublisher(redis_client=redis_client)
    queue_key = settings.redis.notification_queue_key

    reminder_id = uuid7()
    payload = NotificationPayload(
        event_type=NotificationEventType.REMINDER_DUE,
        recipient_chat_id=987654321,
        reminder_id=reminder_id,
        reminder_type=ReminderType.MEDICATION,
        title="Час прийняти ліки",
        description="Препарат: Амоксицилін, дозування 500 мг.",
        strict_schedule=True,
        disable_sound=False,
    )

    # 1. Публікація одиничного повідомлення у Redis
    await publisher.publish(payload)

    # 2. Вичитування повідомлення через BRPOP (як робить бот у фоновому циклі)
    pop_result = await redis_client.brpop(queue_key, timeout=2)
    assert pop_result is not None
    key_name, raw_json = pop_result
    assert key_name.decode("utf-8") if isinstance(key_name, bytes) else key_name == queue_key

    # 3. Десеріалізація та валідація вмісту
    received_payload = NotificationPayload.model_validate_json(raw_json)
    assert received_payload.event_type == NotificationEventType.REMINDER_DUE
    assert received_payload.recipient_chat_id == 987654321
    assert received_payload.reminder_id == reminder_id
    assert received_payload.reminder_type == ReminderType.MEDICATION
    assert received_payload.title == "Час прийняти ліки"
    assert received_payload.description == "Препарат: Амоксицилін, дозування 500 мг."
    assert received_payload.strict_schedule is True

    # 4. Перевірка пакетної відправки через publish_many
    batch = [
        NotificationPayload(
            recipient_chat_id=111,
            title="Дайджест 1",
        ),
        NotificationPayload(
            recipient_chat_id=222,
            title="Дайджест 2",
        ),
    ]
    published_count = await publisher.publish_many(batch)
    assert published_count == 2

    # Черга містить 2 елементи
    length = await redis_client.llen(queue_key)
    assert length == 2
