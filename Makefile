# ==============================================================================
# Reminder App — Makefile команд розробки та автоматизації
# ==============================================================================

.PHONY: test test-cov lint lint-fix format format-check typecheck pre-commit check up down logs migrate help

help:
	@echo "Reminder App — Доступні команди автоматизації:"
	@echo "  make up           - Збірка та запуск усіх контейнерів у фоні"
	@echo "  make down         - Зупинка та видалення контейнерів"
	@echo "  make logs         - Перегляд логів контейнерів у реальному часі"
	@echo "  make test         - Запуск усіх тестів через uv (pytest)"
	@echo "  make test-cov     - Запуск тестів із розрахунком покриття коду (coverage)"
	@echo "  make lint         - Перевірка коду лінтером (ruff check)"
	@echo "  make lint-fix     - Автоматичне виправлення зауважень лінтера (ruff check --fix)"
	@echo "  make format       - Форматування коду (ruff format)"
	@echo "  make format-check - Перевірка форматування коду без змін (ruff format --check)"
	@echo "  make typecheck    - Статична перевірка типів через Mypy"
	@echo "  make pre-commit   - Запуск хуків pre-commit для всіх файлів"
	@echo "  make check        - Повний цикл локальних перевірок (lint, format, typecheck, test, pre-commit)"
	@echo "  make migrate      - Застосування міграцій бази даних через Alembic у контейнері"

# ------------------------------------------------------------------------------
# Тестування
# ------------------------------------------------------------------------------
test:
	uv run --directory backend pytest -v

test-cov:
	uv run --directory backend pytest --cov=src --cov-report=term-missing

# ------------------------------------------------------------------------------
# Лінтинг, форматування та типізація
# ------------------------------------------------------------------------------
lint:
	uv run --directory backend ruff check .

lint-fix:
	uv run --directory backend ruff check --fix .

format:
	uv run --directory backend ruff format .

format-check:
	uv run --directory backend ruff format --check .

typecheck:
	uv run --directory backend mypy src

# ------------------------------------------------------------------------------
# Pre-commit та комплексний чекер
# ------------------------------------------------------------------------------
pre-commit:
	uv run --directory backend pre-commit run --all-files

check: lint format-check typecheck test pre-commit

# ------------------------------------------------------------------------------
# Керування Docker контейнерами
# ------------------------------------------------------------------------------
up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head
