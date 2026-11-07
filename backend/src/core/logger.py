import logging
import sys
from typing import Any

from loguru import logger as logger

from src.core.config import settings


class InterceptHandler(logging.Handler):
    """Перехоплює стандартні логи Python (uvicorn, fastapi, arq, aiogram, sqlalchemy) та перенаправляє в Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame: Any = sys._getframe(2) if hasattr(sys, "_getframe") else logging.currentframe()
        depth = 2
        while frame and (depth == 2 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    """Налаштовує глобальне структуроване логування через Loguru для веб-сервера."""
    logger.remove()

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level> <magenta>{extra}</magenta>"
    )

    logger.add(
        sys.stdout,
        format=console_format,
        level=settings.log.level,
        colorize=True,
        enqueue=True,
    )

    # Придушення надмірного шуму від сторонніх бібліотек
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

    # Приглушуємо дублюючий access log Uvicorn
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False

    # Перехоплення стандартного модуля logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Очищення власних хендлерів сторонніх логерів для уникнення дублювання при спливанні
    for uvicorn_logger in ("uvicorn", "uvicorn.error", "fastapi"):
        logging.getLogger(uvicorn_logger).handlers = []
        logging.getLogger(uvicorn_logger).propagate = True

    if "pytest" in sys.modules:
        return

    app_log_path = settings.log.app_log_path
    app_log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(app_log_path),
        rotation=settings.log.rotation,
        retention=settings.log.retention,
        compression="zip",
        level=settings.log.level,
        enqueue=True,
        encoding="utf-8",
    )


def setup_worker_logging() -> None:
    """Конфігурація структурованого логування спеціально для фонового воркера ARQ."""
    logger.remove()

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level> <magenta>{extra}</magenta>"
    )

    logger.add(
        sys.stdout,
        format=console_format,
        level=settings.log.level,
        colorize=True,
        enqueue=True,
    )

    # Перехоплення стандартного модуля logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Очищення власних хендлерів воркера для уникнення дублювання при спливанні (propagate)
    for worker_logger in ("arq", "arq.worker", "sqlalchemy.engine.Engine"):
        logging.getLogger(worker_logger).handlers = []
        logging.getLogger(worker_logger).propagate = True

    if "pytest" in sys.modules:
        return

    worker_log_path = settings.log.worker_log_path
    worker_log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(worker_log_path),
        rotation=settings.log.rotation,
        retention=settings.log.retention,
        compression="zip",
        level=settings.log.level,
        enqueue=True,
        encoding="utf-8",
    )


def setup_bot_logging() -> None:
    """Конфігурація структурованого логування спеціально для Telegram-бота на базі aiogram."""
    logger.remove()

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level> <magenta>{extra}</magenta>"
    )

    logger.add(
        sys.stdout,
        format=console_format,
        level=settings.log.level,
        colorize=True,
        enqueue=True,
    )

    # Перехоплення стандартного модуля logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Очищення власних хендлерів aiogram для уникнення дублювання при спливанні
    for bot_logger in ("aiogram", "aiogram.event", "aiogram.dispatcher"):
        logging.getLogger(bot_logger).handlers = []
        logging.getLogger(bot_logger).propagate = True

    if "pytest" in sys.modules:
        return

    bot_log_path = settings.log.bot_log_path
    bot_log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(bot_log_path),
        rotation=settings.log.rotation,
        retention=settings.log.retention,
        compression="zip",
        level=settings.log.level,
        enqueue=True,
        encoding="utf-8",
    )
