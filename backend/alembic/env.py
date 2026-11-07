import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Додаємо корінь бекенду в sys.path для коректного імпорту пакетів
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Імпорт моделей модулів для автогенерації Alembic:
import src.modules.users.infrastructure.models  # noqa: F401, E402
import src.modules.finance.infrastructure.models  # noqa: F401, E402
import src.modules.reminders.infrastructure.models  # noqa: F401, E402

from src.core import logger, settings  # noqa: E402
from src.infrastructure.db import Base  # noqa: E402

# Конфігурація Alembic
config = context.config

# Встановлюємо URL підключення з pydantic-settings, якщо він ще не заданий
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.db.url)

# Налаштування логування Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метадані для autogenerate
target_metadata = Base.metadata


def process_revision_directives(
    context: Any,
    revision: Any,
    directives: list[Any],
) -> None:
    """Запобігає генерації порожнього файлу міграції при alembic revision --autogenerate."""
    if config.cmd_opts and getattr(config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("Схема актуальна. Генерацію порожньої міграції скасовано.")


def run_migrations_offline() -> None:
    """Запуск міграцій в 'offline' режимі (генерація SQL-скрипта)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Виконання міграцій на відкритому синхронному з'єднанні."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Створення асинхронного рушія та запуск міграцій."""
    url = config.get_main_option("sqlalchemy.url") or settings.db.url
    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Запуск міграцій в 'online' режимі."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
