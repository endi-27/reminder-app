from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.api.dependencies import register_telegram_user_resolver
from src.api.exception_handlers import setup_exception_handlers
from src.api.middlewares import setup_middlewares
from src.api.v1.router import api_v1_router
from src.core.config import settings
from src.core.database import close_db
from src.core.events import setup_event_bus
from src.core.logger import logger, setup_logging
from src.core.redis import close_redis
from src.modules.users import resolve_user_by_telegram_id


def setup_event_handlers() -> None:
    """Ініціалізація зареєстрованих обробників подій рівня застосунку."""
    setup_event_bus()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Керування життєвим циклом FastAPI додатку."""
    # Startup
    setup_logging()
    logger.info("Ініціалізація бекенду reminder-app ({env})...", env=settings.environment)
    setup_event_handlers()

    yield

    # Shutdown
    logger.info("Завершення роботи бекенду reminder-app...")
    await close_redis()
    await close_db()
    logger.info("Ресурси успішно вивільнено.")


def create_app() -> FastAPI:
    """Фабрика створення екземпляра додатку FastAPI (Composition Root)."""
    application = FastAPI(
        title="Reminder App API",
        description="Асинхронний бекенд платформи розумних нагадувань та моніторингу підписок",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Підключення глобальних HTTP-мідлварів
    setup_middlewares(application)

    # Підключення глобальних обробників винятків
    setup_exception_handlers(application)

    # Підключення роутерів API v1
    application.include_router(api_v1_router)

    # Реєстрація резолвера Telegram-користувача для системи автентифікації
    register_telegram_user_resolver(resolve_user_by_telegram_id)

    @application.get("/", tags=["System"])
    async def root() -> dict[str, Any]:
        """Кореневий ендпоінт перевірки статусу сервісу."""
        return {
            "service": "Reminder App Backend",
            "version": "0.1.0",
            "docs": "/docs",
            "health": f"{settings.api.v1_prefix}/health",
        }

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment in ("development", "dev"),
    )
