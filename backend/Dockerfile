# ==============================================================================
# 1. Етап підготовки та встановлення залежностей (Builder)
# ==============================================================================
FROM python:3.12-slim AS builder-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Копіюємо офіційний бінарник uv
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/

# Копіюємо файл маніфесту залежностей та lock-файл для кешування шарів
COPY pyproject.toml uv.lock ./

# Встановлюємо лише продакшн залежності у віртуальне середовище
RUN uv sync --frozen --no-dev --no-install-project


# ==============================================================================
# 2. Етап для прогону тестів (Test Stage для CI)
# ==============================================================================
FROM builder-base AS test
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY alembic.ini pyproject.toml ./
ENV PATH="/app/.venv/bin:$PATH"
CMD ["pytest", "-v"]


# ==============================================================================
# 3. Фінальний чистий образ для продакшену (Production Runtime)
# ==============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Встановлення curl для docker healthcheck та створення непривілейованого користувача
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 appuser \
    && useradd -u 1000 -g appuser -s /bin/sh appuser \
    && mkdir -p /logs \
    && chown -R appuser:appuser /app /logs

# Копіюємо скомпільоване віртуальне середовище з builder етапу
COPY --from=builder-base --chown=appuser:appuser /app/.venv /app/.venv

# Копіюємо вихідний код додатку та конфігурації
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser alembic.ini pyproject.toml ./

USER appuser

EXPOSE 8000

# Фінальний запуск сервісу через Uvicorn
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
