from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.db.url,
    echo=settings.db.echo,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
    pool_timeout=settings.db.pool_timeout,
    pool_pre_ping=True,
    connect_args={"server_settings": {"timezone": "utc"}},
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронний генератор сесій для ін'єкції залежностей у FastAPI."""
    async with async_session_factory() as session:
        yield session


async def close_db() -> None:
    """Закриття рушія та пулу з'єднань БД при завершенні роботи сервісу."""
    await engine.dispose()
