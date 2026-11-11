from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.context import get_correlation_id
from src.core.exceptions import AppException
from src.core.logger import logger
from src.core.masking import MASKED_VALUE, is_sensitive_key, mask_sensitive_data


def _build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """
    Формує стандартизовану відповідь з єдиною JSON-структурою помилки:
    {"error": {"code": ..., "message": ..., "details": ..., "correlation_id": ...}}.
    """
    content = {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
            "correlation_id": get_correlation_id(),
        }
    }
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=dict(headers) if headers else None,
    )


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Маскує конфіденційні поля у вхідних даних помилок валідації Pydantic."""
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        err_copy = err.copy()
        loc = err_copy.get("loc", ())
        has_sensitive = any(isinstance(part, str) and is_sensitive_key(part) for part in loc)
        if has_sensitive and "input" in err_copy:
            err_copy["input"] = MASKED_VALUE
        elif "input" in err_copy and isinstance(err_copy["input"], (dict, list)):
            err_copy["input"] = mask_sensitive_data(err_copy["input"])
        sanitized.append(err_copy)
    return sanitized


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Обробник доменних та сервісних винятків AppException."""
    if exc.status_code >= 500:
        logger.opt(exception=exc).error(
            "AppException {status} ({code}) на {path}: {msg}",
            status=exc.status_code,
            code=exc.error_code,
            path=request.url.path,
            msg=exc.message,
        )
    else:
        logger.warning(
            "AppException {status} ({code}) на {path}: {msg}",
            status=exc.status_code,
            code=exc.error_code,
            path=request.url.path,
            msg=exc.message,
        )

    headers = getattr(exc, "headers", None)
    return _build_error_response(
        status_code=exc.status_code,
        code=exc.error_code,
        message=exc.message,
        details=exc.details,
        headers=headers,
    )


async def stale_data_error_handler(request: Request, exc: StaleDataError) -> JSONResponse:
    """
    Обробник конфліктів оптимістичного блокування (OCC) SQLAlchemy (Інваріант 11 AGENTS.md).
    Транслює помилку версійності у HTTP 409 Conflict з кодом OPTIMISTIC_LOCK_CONFLICT.
    """
    logger.warning(
        "Конфлікт оптимістичного блокування OCC (StaleDataError) на {path}: {err}",
        path=request.url.path,
        err=str(exc),
    )
    return _build_error_response(
        status_code=409,
        code="OPTIMISTIC_LOCK_CONFLICT",
        message="Дані було змінено іншим процесом або фоновим воркером. Оновіть дані та спробуйте ще раз.",
        details={"reason": "concurrent_modification"},
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Обробник порушень цілісності бази даних PostgreSQL."""
    orig = exc.orig
    pgcode = getattr(orig, "sqlstate", getattr(orig, "pgcode", None))
    orig_msg = str(orig or exc).lower()

    logger.warning(
        "IntegrityError ({code}) на {path}: {msg}",
        code=pgcode,
        path=request.url.path,
        msg=str(orig or exc),
    )

    status_code = 409
    if pgcode == "23503" and (request.method == "DELETE" or "is still referenced from" in orig_msg):
        code = "RESOURCE_LOCKED"
        message = "Неможливо остаточно видалити запис, оскільки він використовується в пов'язаних даних."
    else:
        code = "CONFLICT"
        message = "Порушення цілісності або унікальності даних при збереженні в базу."

    details = {"pgcode": pgcode} if pgcode else {}
    return _build_error_response(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Обробник помилок валідації запитів FastAPI/Pydantic із маскуванням паролів і токенів."""
    raw_errors: list[dict[str, Any]] = jsonable_encoder(exc.errors())
    sanitized_errors = _sanitize_validation_errors(raw_errors)

    logger.warning(
        "422 Validation Error | Path: {path} | Errors: {errors}",
        path=request.url.path,
        errors=sanitized_errors,
    )
    return _build_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Помилка валідації вхідних даних.",
        details={"errors": sanitized_errors},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Обробник стандартних HTTP-винятків Starlette/FastAPI."""
    error_code_map: dict[int, str] = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        408: "REQUEST_TIMEOUT",
        409: "CONFLICT",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "UNPROCESSABLE_ENTITY",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }

    details: dict[str, Any]
    if isinstance(exc.detail, dict):
        code = (
            exc.detail.get("code")
            or exc.detail.get("error_code")
            or error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        )
        message = str(exc.detail.get("message") or "Сталася помилка обробки запиту.")
        details = {k: v for k, v in exc.detail.items() if k not in ("code", "error_code", "message")}
    else:
        code = error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        details = {}

    if exc.status_code >= 500:
        logger.error(
            "HTTPException {status} ({code}) на {path}: {detail}",
            status=exc.status_code,
            code=code,
            path=request.url.path,
            detail=message,
        )
    else:
        logger.warning(
            "HTTPException {status} ({code}) на {path}: {detail}",
            status=exc.status_code,
            code=code,
            path=request.url.path,
            detail=message,
        )

    return _build_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
        headers=exc.headers,
    )


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Обробник перевищення ліміту частоти запитів (429 Too Many Requests)."""
    client_ip = request.client.host if request.client else "unknown"
    logger.warning(
        "429 Too Many Requests | Path: {path} | IP: {ip} | Limit: {detail}",
        path=request.url.path,
        ip=client_ip,
        detail=exc.detail,
    )
    headers = getattr(exc, "headers", None) or {}
    return _build_error_response(
        status_code=429,
        code="TOO_MANY_REQUESTS",
        message="Перевищено допустимий ліміт запитів. Будь ласка, зачекайте перед повторною спробою.",
        details={"limit": exc.detail},
        headers=headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обробник непередбачених критичних системних помилок 500."""
    logger.exception(
        "Неперехоплена системна помилка 500 на {method} {path}: {err}",
        method=request.method,
        path=request.url.path,
        err=str(exc),
    )
    return _build_error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Сталася неочікувана внутрішня помилка сервера.",
        details={},
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Реєстрація всіх глобальних обробників винятків у FastAPI додатку."""
    app.add_exception_handler(AppException, cast(Any, app_exception_handler))
    app.add_exception_handler(StarletteHTTPException, cast(Any, http_exception_handler))
    app.add_exception_handler(RateLimitExceeded, cast(Any, rate_limit_exceeded_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_exception_handler))
    app.add_exception_handler(IntegrityError, cast(Any, integrity_error_handler))
    app.add_exception_handler(StaleDataError, cast(Any, stale_data_error_handler))
    app.add_exception_handler(500, unhandled_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
