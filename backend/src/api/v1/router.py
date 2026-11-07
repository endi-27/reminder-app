from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.redis import RedisClient, get_redis_client
from src.modules.finance.router import finance_router
from src.modules.reminders.router import reminders_router
from src.modules.users.router import users_router


class HealthCheckResponse(BaseModel):
    """Схема відповіді стану працездатності системи (Health Check)."""

    status: Annotated[str, Field(description="Загальний статус системи (healthy або unhealthy)")]
    database: Annotated[str, Field(description="Статус підключення до PostgreSQL (ok або опис помилки)")]
    redis: Annotated[str, Field(description="Статус підключення до Redis (ok або опис помилки)")]
    version: Annotated[str, Field(description="Версія сервісу Reminder App")] = "0.1.0"


api_v1_router = APIRouter(prefix="/api/v1")


@api_v1_router.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["System"],
    summary="Перевірка працездатності сервісу",
    description="Валідує доступність бази даних PostgreSQL та сховища/черги Redis.",
)
async def health_check(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[RedisClient, Depends(get_redis_client)],
) -> HealthCheckResponse:
    """
    Комплексна перевірка працездатності сервісу (Health Check).

    Виконує тестовий SQL-запит (SELECT 1) у PostgreSQL та PING у Redis.
    У разі недоступності будь-якого критичного компонента встановлює статус HTTP 503.
    """
    db_status = "ok"
    redis_status = "ok"
    is_healthy = True

    # 1. Перевірка бази даних PostgreSQL
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc}"
        is_healthy = False

    # 2. Перевірка Redis
    try:
        await redis.ping()
    except Exception as exc:
        redis_status = f"unhealthy: {exc}"
        is_healthy = False

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        system_status = "unhealthy"
    else:
        system_status = "healthy"

    return HealthCheckResponse(
        status=system_status,
        database=db_status,
        redis=redis_status,
        version="0.1.0",
    )


# ==============================================================================
# Точки підключення доменних роутерів платформи:
# Бізнес-модуль користувачів
api_v1_router.include_router(users_router)
# Бізнес-модуль фінансів
api_v1_router.include_router(finance_router)
# Бізнес-модуль нагадувань
api_v1_router.include_router(reminders_router)
# ==============================================================================
