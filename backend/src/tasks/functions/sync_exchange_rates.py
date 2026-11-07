from typing import Any

from src.core import logger
from src.infrastructure.db.uow import SqlAlchemyUnitOfWork
from src.modules.finance.public import FinancePublicGateway


async def cron_sync_exchange_rates(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Періодична задача ARQ для синхронізації банківських курсів валют (НБУ, Monobank, ПриватБанк).

    Виконується кожні 6 годин (а також при старті воркера), отримуючи актуальні курси
    валют та зберігаючи їх у режимі Append-Only у таблиці exchange_rates.
    """
    logger.info("Початок виконання періодичної задачі синхронізації курсів валют.")

    async with SqlAlchemyUnitOfWork() as uow:
        gateway = FinancePublicGateway(session=uow.session, uow=uow)
        sync_result = await gateway.sync_all_rates()
        await uow.commit()

    logger.info(
        "Завершено синхронізацію курсів валют: успішних постачальників {success}, "
        "помилок {failed}, збережено записів курсів {synced}",
        success=len(sync_result.providers_succeeded),
        failed=len(sync_result.providers_failed),
        synced=sync_result.synced_count,
    )
    return sync_result.model_dump()
