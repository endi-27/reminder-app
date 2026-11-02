# Reminder App — Self-Hosted Персональний Сервіс Нагадувань

**Reminder App** — це автономний, мультикористувацький (multi-user ready) сервіс розумних нагадувань, побудований за принципами **Domain-Driven Design (DDD)** та **Модульного Моноліту (Modular Monolith)** із прагматичним **CQRS**. Сервіс інтегрується з **Telegram Bot (`aiogram 3.x`)** у режимі Long Polling у закритій мережі (без потреби у зовнішніх портах, домені чи SSL-сертифікатах) та споживає ~200 МБ оперативної пам'яті.

---

## 🚀 Ключові можливості

* **5 спеціалізованих типів нагадувань**:
  1. **`ANNIVERSARY`** — дні народження, річниці та пам'ятні дати з каскадними попередженнями (за 14, 7, 3, 1, 0 днів), розрахунком віку та автоматичною обробкою 29 лютого.
  2. **`OPEN_TASK`** — задачі беклогу без жорсткого дедлайну, що агрегуються у ранкові/вечірні дайджести замість спаму.
  3. **`DEADLINE_TASK`** — термінові справи з фіксованим дедлайном та автоматичною математичною ескалацією пріоритету (`LOW` $\rightarrow$ `MEDIUM` $\rightarrow$ `HIGH` $\rightarrow$ `CRITICAL`) у міру наближення терміну.
  4. **`SUBSCRIPTION`** — регулярні платежі та підписки з підтримкою:
     * **Пробних періодів (Trial)** із попередженнями про закінчення та автопереходом у платний тариф.
     * **Акційних знижок на перші $X$ платежів** із лічильником залишкових циклів та попередженням перед переходом на повну ціну.
     * **Мультивалютності (`UAH`, `USD`, `EUR`)** з конвертацією за картковим курсом обраного банку (Monobank, ПриватБанк, НБУ) та автоматичним fallback на курс НБУ, якщо курс банку не оновлювався > 48 годин.
  5. **`MEDICATION`** — курсовий або безстроковий/пожиттєвий прийом ліків та вітамінів із журналом дотримання (`medication_intake_logs`), інтерактивними кнопками `[💊 Прийняв]`, `[⏰ +15 хв]`, `[❌ Пропустив]` та режимом **`strict_schedule`** (ігнорування «Тихих годин» для критичних нічних прийомів антибіотиків).
* **6 уніфікованих логік планування (`ScheduleLogicType`)** та безстатусний алгоритм **Time-Series Projection** для розрахунку каскадів `lead_times` без вразливих індексів масивів.
* **Захист від Alert Fatigue**: індивідуальні часові пояси (IANA Timezone) та вікно «Тихих годин» (`QuietHoursWindow`) для кожного користувача.

---

## 🛠️ Технологічний стек

| Компонент | Технологія | Призначення |
| :--- | :--- | :--- |
| **Мова та рантайм** | Python 3.12+ (`asyncio`) | Повністю асинхронне виконання |
| **HTTP API** | FastAPI + Pydantic v2 | REST API, валідація DTO (`Annotated`), OpenAPI 3.1 |
| **Telegram Bot** | aiogram 3.x (Long Polling) | Інтерактивний UI, інлайн-кнопки, `BRPOP` споживач черги |
| **База даних** | PostgreSQL 16 | Первинні ключі **UUIDv7**, Single Table Inheritance (STI), JSONB |
| **ORM та Міграції** | SQLAlchemy 2.0 (Async) + Alembic | Строгий `lazy="raise"`, Optimistic Concurrency Control (`version`) |
| **Черги та Шедулер**| Redis 7 (Alpine) + ARQ | Хвилинний Cron-полер (`SKIP LOCKED`), черга доставки в бот |
| **Інструментарій** | `uv`, `ruff`, `mypy`, `pytest`, `Loguru` | Керування пакетами, лінтинг, типізація, тестування, логування |

---

## 📚 Документація проєкту (Single Source of Truth)

* **[docs/CONTEXT.md](./docs/CONTEXT.md)** — Глосарій єдиної доменної мови (Ubiquitous Language).
* **[docs/SPECIFICATION.md](./docs/SPECIFICATION.md)** — Повна бізнес-специфікація, матриця сумісності 5 типів та 6 логік, формули ескалації та Time-Series Projection.
* **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — Системна архітектура, пайплайн пошуку та доставки сповіщень, фонові крон-задачі ARQ.
* **[docs/DATABASE.md](./docs/DATABASE.md)** — ER-діаграма, детальний опис усіх таблиць і полів, приклади JSONB для всіх 8 комбінацій та готовий SQL DDL-скрипт.
* **[docs/PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md)** — Фізична структура каталогів, опис системних пакетів та шаблони модулів.
* **[AGENTS.md](./AGENTS.md)** — Конституція та 17 обов'язкових інваріантів розробки для AI-агентів і розробників.
* **[CONTRIBUTING.md](./CONTRIBUTING.md)** — Стандарти Git (Conventional Commits, гілки, Pull Requests, pre-commit).

---

## ⚡ Швидкий старт та команди розробки

### 1. Запуск інфраструктури через Docker Compose
```bash
cp .env.example .env
docker compose up -d
```

### 2. Локальна розробка та перевірка якості коду (через `uv`)
Усі команди виконуються з використанням пакетного менеджера `uv`:

```bash
# Встановлення залежностей та pre-commit хуків
uv run --directory backend pre-commit install

# Запуск лінтера та автоформатування Ruff
uv run --directory backend ruff check .
uv run --directory backend ruff format .

# Перевірка статичної типізації MyPy
uv run --directory backend mypy src

# Виконання міграцій бази даних Alembic
uv run --directory backend alembic upgrade head

# Запуск тестів (unit / integration / api)
uv run --directory backend pytest
```

### 3. Доступ до Swagger UI (у закритій мережі VPS)
Оскільки сервіс не відкриває зовнішніх портів у світ, для перегляду документації API `/docs` на віддаленому сервері використовуйте SSH-тунель:
```bash
ssh -L 8000:localhost:8000 user@your-vps-ip
# Після цього відкрийте http://localhost:8000/docs у браузері
```
