# Інструкції з внесення змін та стандарти Git (CONTRIBUTING)

Цей документ визначає стандарти Git-комітів, правила найменування гілок, регламент Pull Requests та автоматизацію перевірки якості коду для проєкту **Reminder App**.

---

## 1. Стандарти Git-комітів (Conventional Commits)

У проєкті використовується стандарт **Conventional Commits** англійською мовою.

### 1.1. Формат повідомлення коміту:
```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

* **Мова комітів:** Англійська (`en-US`).
* **Дієслова:** Наказовий спосіб теперішнього часу (`add`, `update`, `fix`, `refactor`, `remove`, `document` замість `added`/`adding`).
* **Регістр:** Повідомлення починається з малої літери, без крапки в кінці заголовка.

---

### 1.2. Дозволені типи (`type`):
* `feat`: Новий функціонал, доменний агрегат, хендлер бота або ендпоінт API.
* `fix`: Виправлення бага чи помилки в розрахунках розкладу, боті або API.
* `docs`: Зміни в документації (`docs/CONTEXT.md`, `docs/SPECIFICATION.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/PROJECT_STRUCTURE.md`).
* `refactor`: Рефакторинг коду без зміни зовнішньої поведінки чи виправлення багів.
* `test`: Додавання або виправлення автотестів (`test(unit): ...`, `test(integration): ...`, `test(api): ...`).
* `chore`: Зміни конфігурацій, оновлення залежностей (`pyproject.toml`), налаштування Docker або лінтерів.
* `perf`: Оптимізація швидкодії SQL-запитів шедулера, індексів або воркерів.
* `ci`: Зміни у пайплайнах CI/CD або GitHub Actions.

---

### 1.3. Дозволені скоупи (`scope`):
* **Системні та інфраструктурні:** `(core)`, `(infra)`, `(db)`, `(api)`, `(tasks)`, `(bot)`, `(docs)`, `(deps)`, `(docker)`.
* **Бізнес-модулі:** `(users)`, `(reminders)`, `(finance)`, `(notifications)`.
* **Тестування:** `(unit)`, `(integration)`.

---

### 1.4. Приклади коректних комітів:
* `docs(db): add postgresql 16 schema specification and 8 jsonb schedule examples`
* `feat(reminders): implement stateless time-series projection for lead times`
* `feat(finance): add monobank rate collector and 48h nbu fallback engine`
* `feat(bot): implement inline action callbacks for medication intake logs`
* `fix(tasks): handle quiet hours override for strict schedule medications`
* `test(unit): add fake uow tests for subscription promotional discount cycles`
* `chore(deps): configure ruff, mypy, and pytest in pyproject.toml`

---

## 2. Правила роботи з гілками та Pull Requests

1. **Іменування гілок:** Усі нові задачі розробляються в окремих гілках від актуального `main`:
   * `feature/<feature-name>` — для нового функціоналу (наприклад, `feature/medication-adherence-log`).
   * `bugfix/<bug-name>` — для виправлення дефектів (наприклад, `bugfix/leap-year-feb-29-policy`).
   * `docs/<docs-topic>` — для змін у системній документації.
   * `refactor/<refactoring-scope>` — для структурного рефакторингу коду.
2. **Злиття через Pull Request (Trunk-Based Development):**
   * Гілки мають бути короткими та сфокусованими на одній задачі.
   * Перед злиттям у `main` обов'язкове успішне проходження лінтерів (`ruff check`, `ruff format`), статичної типізації (`mypy`) та автотестів (`pytest`), а також відповідність усім 17 інваріантам із [`AGENTS.md`](./AGENTS.md).
3. **Безпечні міграції БД (Expand & Contract):**
   * Усі зміни схеми PostgreSQL оформлюються через міграції Alembic у `backend/alembic/versions/` і перевіряються на коректність як `upgrade`, так і `downgrade`.

---

## 3. Автоматизація якості коду (Pre-commit хуки)

Для запобігання потраплянню невідформатованого коду, помилок типізації або синтаксичних дефектів у репозиторій використовується **pre-commit**.

### 3.1. Встановлення хуків у локальний Git:
```bash
uv run --directory backend pre-commit install
```

### 3.2. Що перевіряється автоматично при кожному `git commit`:
1. **Санітарні перевірки репозиторію:**
   * Видалення зайвих пробілів у кінці рядків (`trailing-whitespace`).
   * Гарантія порожнього рядка в кінці файлів (`end-of-file-fixer`).
   * Перевірка синтаксису YAML та TOML файлів (`check-yaml`, `check-toml`).
   * Захист від коміту великих файлів понад 1 МБ (`check-added-large-files`).
   * Захист від маркерів невирішених конфліктів злиття (`check-merge-conflict`).
2. **Перевірки Python-коду (`backend/`):**
   * `uv run --directory backend ruff check --fix` — лінтинг з автовиправленням.
   * `uv run --directory backend ruff format` — стандартизоване форматування коду.
   * `uv run --directory backend mypy src` — сувора перевірка статичної типізації.

### 3.3. Ручний запуск перевірок на всіх файлах:
```bash
uv run --directory backend pre-commit run --all-files
```
