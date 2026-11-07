import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ініціалізація змінних тестового оточення перед будь-якими імпортами конфігурації
os.environ.setdefault("APP_CONFIG__ENVIRONMENT", "test")
os.environ.setdefault("APP_CONFIG__DB__NAME", "reminder_app_test")

if os.environ.get("APP_CONFIG__AUTH__BCRYPT_ROUNDS") in (None, "12"):
    os.environ["APP_CONFIG__AUTH__BCRYPT_ROUNDS"] = "4"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from scripts.seed_superadmin import seed_superadmin
from src.core import Settings, get_settings, settings
from src.core.database import get_db_session
from src.core.redis import RedisClient, close_redis, get_redis_client
from src.main import app

# Очищуємо кеш синглтона get_settings, щоб переконатися у підтягуванні тестових параметрів
get_settings.cache_clear()


@pytest.fixture(scope="session")
async def setup_test_database() -> AsyncGenerator[None, None]:
    """
    Гарантує створення виділеної тестової бази даних 'reminder_app_test' (Інваріант 16)
    та застосування актуальних Alembic міграцій один раз на сесію запусків.
    """
    current_settings = get_settings()
    if "test" not in current_settings.db.name.lower() or current_settings.db.name == "reminder_app":
        msg = (
            f"Критична помилка безпеки: тести намагаються використати робочу базу даних "
            f"'{current_settings.db.name}'. Назва тестової БД повинна містити 'test' "
            f"та не збігатися з основною базою 'reminder_app'!"
        )
        raise RuntimeError(msg)

    # 1. Підключення до системної БД 'postgres' для перевірки та створення reminder_app_test
    maintenance_url = (
        f"postgresql+asyncpg://{current_settings.db.user}:{current_settings.db.password}@"
        f"{current_settings.db.host}:{current_settings.db.port}/postgres"
    )
    admin_engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": current_settings.db.name},
        )
        if not exists:
            try:
                await conn.execute(
                    text(f'CREATE DATABASE "{current_settings.db.name}" OWNER "{current_settings.db.user}"')
                )
            except Exception as exc:
                if "already exists" not in str(exc).lower() and "duplicate_database" not in str(exc).lower():
                    raise
    await admin_engine.dispose()

    # 2. Застосування міграцій Alembic до тестової БД
    def _run_migrations() -> None:
        from alembic.config import Config

        from alembic import command

        backend_dir = Path(__file__).resolve().parent.parent
        ini_path = backend_dir / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", current_settings.db.url)
        command.upgrade(alembic_cfg, "head")

    await asyncio.to_thread(_run_migrations)

    # 3. Ідемпотентне сідування суперадміністратора у тестову БД
    await seed_superadmin()

    yield


@pytest.fixture(scope="session")
async def test_engine(setup_test_database: None) -> AsyncGenerator[AsyncEngine, None]:
    """
    Спільний асинхронний рушій SQLAlchemy для підключення до тестової БД.
    Використовує NullPool для уникнення збереження незакритих сесій у пулі.
    """
    _ = setup_test_database
    engine = create_async_engine(
        get_settings().db.url,
        poolclass=NullPool,
        connect_args={"server_settings": {"timezone": "utc"}},
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Ізольована сесія бази даних для кожного окремого тесту (Інваріант 16).
    Працює в транзакційному режимі Savepoint (join_transaction_mode="create_savepoint")
    та гарантовано відкочує всі внесені зміни після завершення тесту.
    """
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
        async with session_factory() as session:
            yield session
        await transaction.rollback()


@pytest.fixture
async def redis_client() -> AsyncGenerator[RedisClient, None]:
    """
    Підключення до Redis для тестів з гарантованим очищенням черги повідомлень.
    """
    client = get_redis_client()
    queue_key = settings.redis.notification_queue_key
    await client.delete(queue_key)
    yield client
    await client.delete(queue_key)
    await close_redis()


@pytest.fixture
def mock_task_dispatcher() -> Generator[AsyncMock, None, None]:
    """
    Мок постановки фонових задач у чергу ARQ для ізольованих тестів.
    """
    with patch(
        "src.tasks.dispatcher.TaskDispatcher._enqueue_task",
        new_callable=AsyncMock,
        return_value="mocked-job-id-uuid",
    ) as mock_enqueue:
        yield mock_enqueue


@pytest.fixture
def test_settings() -> Settings:
    """Повертає актуальні налаштування для тестового середовища."""
    return get_settings()


@pytest.fixture
async def api_client(
    db_session: AsyncSession,
    redis_client: RedisClient,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Асинхронний HTTP-клієнт для E2E та API-тестування FastAPI ендпоінтів.
    Підміняє фабрики отримання сесії БД та Redis на ізольовані тестові фікстури.
    """

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_get_redis_client() -> RedisClient:
        return redis_client

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_redis_client] = _override_get_redis_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
