# Reminder App — Self-Hosted Персональний Сервіс Нагадувань

**Reminder App** — це автономний, мультикористувацький (multi-user ready) сервіс розумних нагадувань, побудований за принципами **Domain-Driven Design (DDD)** та **Модульного Моноліту (Modular Monolith)** із прагматичним **CQRS**. Сервіс інтегрується з **Telegram Bot (`aiogram 3.x`)** у режимі Long Polling у закритій мережі (без потреби у зовнішніх портах, публічному домені чи SSL-сертифікатах) та споживає ~200 МБ оперативної пам'яті.

---

## 🚀 Ключові можливості

* **5 спеціалізованих типів нагадувань**:
  1. **`ANNIVERSARY`** — дні народження, річниці та пам'ятні дати з каскадними завчасними сповіщеннями (за 14, 7, 3, 1, 0 днів), розрахунком віку та автоматичною обробкою 29 лютого.
  2. **`OPEN_TASK`** — задачі беклогу без жорсткого дедлайну, що автоматично агрегуються у ранкові/вечірні дайджести замість спаму.
  3. **`DEADLINE_TASK`** — термінові справи з дедлайном та автоматичною математичною ескалацією пріоритету (`LOW` $\rightarrow$ `MEDIUM` $\rightarrow$ `HIGH` $\rightarrow$ `CRITICAL`) у міру наближення терміну.
  4. **`SUBSCRIPTION`** — регулярні платежі та підписки з підтримкою:
     * **Пробних періодів (Trial)** із завчасними попередженнями про закінчення та автоматичним переходом у платний тариф.
     * **Акційних знижок на перші $X$ платежів** із лічильником залишкових циклів та попередженням перед переходом на повну ціну.
     * **Мультивалютності (`UAH`, `USD`, `EUR`)** з конвертацією за картковим курсом обраного банку (Monobank, ПриватБанк, НБУ) та автоматичним fallback на курс НБУ, якщо курс банку застарів (> 48 годин).
  5. **`MEDICATION`** — курсовий або безстроковий прийом ліків та вітамінів із журналом дотримання (`medication_intake_logs`), інтерактивними кнопками `[💊 Прийняв]`, `[⏰ +15 хв]`, `[❌ Пропустив]` та режимом **`strict_schedule`** (ігнорування «Тихих годин» для критичних нічних прийомів антибіотиків).
* **Повноцінний Telegram Bot UI (`src/bot/`)**:
  * 7 канонічних команд меню: `/start`, `/new`, `/list`, `/rates`, `/settings`, `/cancel`, `/help`.
  * 5 покрокових FSM-майстрів створення нагадувань із валідацією та швидкими кнопками вибору.
  * Інтерактивні дії на повідомленнях (`edit_message_text`) із захистом від подвійного натискання.
  * Керування персональними налаштуваннями (тихі години, часовий пояс IANA, пріоритетний банк, автоескалація).
* **Повна розв'язка шарів (Notification Decoupling)**:
  * Бекенд та шедулер ARQ генерують виключно структуровані JSON-події (`NotificationPayload`) без жодного UI-тексту, емодзі чи `callback_data` у Redis-чергу `queue:notifications:telegram`.
  * Бот-консюмер (`RedisNotificationConsumer`) самостійно вичитує події через `BRPOP`, рендерить HTML-повідомлення та генерує клавіатури дій із типізованими `CallbackData`.
* **6 уніфікованих логік планування (`ScheduleLogicType`)** та детермінований алгоритм **Time-Series Projection** для розрахунку каскадів `lead_times` без збереження вразливих індексів елементів.
* **Захист від Alert Fatigue**: індивідуальні часові пояси та вікно «Тихих годин» (`QuietHoursWindow`) для кожного користувача.

---

## 🛠️ Технологічний стек

| Компонент | Технологія | Призначення |
| :--- | :--- | :--- |
| **Мова та рантайм** | Python 3.12+ (`asyncio`) | Повністю асинхронне виконання |
| **HTTP API** | FastAPI + Pydantic v2 | REST API, валідація DTO (`Annotated`), OpenAPI 3.1 (`src/api/main.py`) |
| **Telegram Bot** | aiogram 3.x (Long Polling) | Фабрика `src/bot/bot.py`, раннер `src/bot/main.py`, FSM, Redis Consumer |
| **База даних** | PostgreSQL 16 | Первинні ключі **UUIDv7**, Single Table Inheritance (STI), JSONB |
| **ORM та Міграції** | SQLAlchemy 2.0 (Async) + Alembic | Строгий `lazy="raise"`, Optimistic Concurrency Control (`version`) |
| **Черги та Шедулер**| Redis 7 (Alpine) + ARQ | Хвилинний Cron-полер (`SKIP LOCKED`), черга доставки (`src/tasks/worker.py`) |
| **Інструментарій** | `uv`, `ruff`, `mypy`, `pytest`, `Loguru` | Пакетний менеджер, лінтинг, статична типізація, тести, логування |

---

## 📚 Документація проєкту (Single Source of Truth)

* **[docs/CONTEXT.md](./docs/CONTEXT.md)** — Глосарій єдиної доменної мови (Ubiquitous Language).
* **[docs/SPECIFICATION.md](./docs/SPECIFICATION.md)** — Повна бізнес-специфікація, матриця сумісності 5 типів та 6 логік, формули ескалації та Time-Series Projection.
* **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — Системна архітектура, пайплайн пошуку та доставки сповіщень, фонові крон-задачі ARQ, розв'язка презентаційного шару.
* **[docs/DATABASE.md](./docs/DATABASE.md)** — ER-діаграма, детальний опис усіх таблиць і полів, приклади JSONB для всіх 8 комбінацій та готовий SQL DDL-скрипт.
* **[docs/PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md)** — Фізична структура каталогів, точки входу адаптерів (`src/api/`, `src/bot/`, `src/tasks/`) та шаблони модулів.
* **[AGENTS.md](./AGENTS.md)** — Конституція та 17 обов'язкових інваріантів розробки для AI-агентів і розробників.
* **[CONTRIBUTING.md](./CONTRIBUTING.md)** — Стандарти Git (Conventional Commits, гілки, Pull Requests, pre-commit).

---

## ⚡ Швидкий старт та розгортання

### 1. Запуск усіх сервісів через Docker Compose
```bash
# 1. Створення файлу оточення з налаштуваннями
cp .env.example .env
# Заповніть токен вашого Telegram-бота в .env (APP_CONFIG__BOT__TOKEN)

# 2. Збірка та запуск усіх контейнерів у фоновому режимі
docker compose up --build -d

# 3. Перевірка статусу контейнерів
docker compose ps
```

До складу системи входять 7 оркестрованих контейнерів:
1. `reminder_postgres` — СУБД PostgreSQL 16 із готовою схемою на базі UUIDv7.
2. `reminder_redis` — In-memory брокер повідомлень (бази 0: дефолт, 1: кеш курсів, 2: тестова, 3: черга сповіщень, 4: FSM сховище).
3. `reminder_migrator` — Автоматичне накатування міграцій Alembic до `head`.
4. `reminder_backend` — Асинхронний REST API сервер на FastAPI (`src.api.main:app`).
5. `reminder_worker` — Фоновий шедулер ARQ (хвилинний полер нагадувань + регулярна синхронізація курсів банків).
6. `reminder_bot` — Telegram-бот на `aiogram 3.x` (Long Polling + фоновий споживач подій `RedisNotificationConsumer`).
7. `reminder_db_backup` — Автоматичне щодобове резервне копіювання бази даних у `backups/`.

---

### 2. Локальна розробка та перевірка якості коду (через `uv`)
Усі команди виконуються через пакетний менеджер `uv`:

```bash
# Встановлення залежностей та pre-commit хуків
uv run --directory backend pre-commit install

# Комплексна перевірка статичної типізації (Pyright + Mypy)
uvx --from pyright pyright --pythonpath backend/.venv/bin/python backend/src backend/tests backend/scripts
uv run --directory backend mypy src

# Перевірка лінтером та форматуванням Ruff
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .

# Запуск повного набору тестів (Unit + Integration + FSM)
uv run --directory backend pytest -q

# Застосування міграцій Alembic
uv run --directory backend alembic upgrade head
```

---

### 3. Доступ до Swagger UI (у закритій мережі VPS)
Оскільки бекенд не відкриває публічних портів у світ задля безпеки, для перегляду Swagger UI (`/docs`) на віддаленому сервері використовуйте безпечний SSH-тунель:
```bash
ssh -L 8000:localhost:8000 user@your-vps-ip
# Після цього відкрийте http://localhost:8000/docs у вашому браузері
```
