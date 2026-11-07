from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.uow import SqlAlchemyUnitOfWork


@pytest.fixture
async def integration_uow(db_session: AsyncSession) -> AsyncGenerator[SqlAlchemyUnitOfWork, None]:
    """
    Екземпляр SqlAlchemyUnitOfWork для інтеграційних тестів з активною транзакційною сесією Savepoint.
    """
    uow = SqlAlchemyUnitOfWork(session=db_session)
    async with uow:
        yield uow
