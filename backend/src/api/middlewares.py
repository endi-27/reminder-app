import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from uuid6 import uuid7
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.core.config import settings
from src.core.context import (
    set_correlation_id,
    set_current_user_id,
    set_current_username,
)
from src.core.limiter import limiter
from src.core.logger import logger


async def request_logger_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    Мідлвар контекстного логування та трасування кожного HTTP-запиту.

    Генерує або витягує ідентифікатор кореляції (UUIDv7), заміряє тривалість
    виконання запиту та гарантовано очищує контекстні змінні в блоці finally.
    """
    incoming_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")
    correlation_id = incoming_id.strip() if incoming_id and incoming_id.strip() else str(uuid7())

    set_correlation_id(correlation_id)
    client_ip = request.client.host if request.client else "unknown"

    with logger.contextualize(correlation_id=correlation_id, client_ip=client_ip):
        start_time = time.perf_counter()
        logger.info("Запит розпочато: {method} {path}", method=request.method, path=request.url.path)

        try:
            response: Response = await call_next(request)
            process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

            logger.info(
                "Запит завершено: {method} {path} | Статус: {status} | Час: {time}ms",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                time=process_time_ms,
            )

            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Request-ID"] = correlation_id
            response.headers["X-Process-Time"] = f"{process_time_ms}ms"

            return response
        except Exception as exc:
            process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.opt(exception=exc).error(
                "Помилка виконання запиту: {method} {path} | Час: {time}ms",
                method=request.method,
                path=request.url.path,
                time=process_time_ms,
            )
            raise
        finally:
            set_correlation_id(None)
            set_current_user_id(None)
            set_current_username(None)


async def no_cache_response_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Заборона збереження відповідей REST API у клієнтському та проміжному кеші."""
    response: Response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def setup_middlewares(app: FastAPI) -> None:
    """Підключення глобальних HTTP-мідлварів до екземпляра додатку."""
    app.middleware("http")(no_cache_response_middleware)
    app.middleware("http")(request_logger_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Прив'язка SlowAPI Limiter до стану додатку
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    # ProxyHeadersMiddleware для коректного визначення IP клієнта за Nginx зворотним проксі
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
