# AGENTS.md — Архітектурна конституція та стандарти для AI-агентів (Reminder App)

Цей документ є верховним регламентом (конституцією) репозиторію **Reminder App**: він визначає глобальні інваріанти, технологічний стек, правила роботи з доменом і базою даних та обов'язковий чек-лист самоконтролю для AI-асистентів.

---

## 1. 🗺️ Джерела істини (Single Source of Truth — SSOT)

Перед початком будь-якої задачі агент зобов'язаний звірятися з канонічною документацією проєкту у директорії `docs/`:
* **[`docs/CONTEXT.md`](./docs/CONTEXT.md)** — Єдина доменна мова (Ubiquitous Language). Заборонено вигадувати синоніми для доменних сутностей, полів чи статусів.
* **[`docs/SPECIFICATION.md`](./docs/SPECIFICATION.md)** — Бізнес-правила 5 типів нагадувань, матриця сумісності з 6 логіками планування, формула динамічної ескалації пріоритету та алгоритм Time-Series Projection.
* **[`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)** — Архітектура доставки сповіщень, взаємодія FastAPI + ARQ + Redis + aiogram (Long Polling), фонові крон-задачі.
* **[`docs/DATABASE.md`](./docs/DATABASE.md)** — Канонічна схема PostgreSQL 16 (UUIDv7, Single Table Inheritance, ER-діаграма, 8 комбінацій JSONB `schedule_config` та `lead_times`, DDL).
* **[`docs/PROJECT_STRUCTURE.md`](./docs/PROJECT_STRUCTURE.md)** — Фізична організація папок та шаблони модулів у `backend/src/`.

### Guardrails документації:
1. Документи домену та схеми БД змінюються **тільки за прямим запитом або погодженням користувача**.
2. Усі діаграми в документації оформлюються **виключно у форматі Mermaid** (ASCII-псевдографіка для схем і потоків заборонена).

---

## 2. ⚙️ Архітектурний контекст та стек

Сервіс побудований як **асинхронний модульний моноліт (Modular Monolith)** із використанням **DDD** та **прагматичного CQRS**:
* **Мова та рантайм:** Python 3.12+ (`asyncio`)
* **HTTP фреймворк:** FastAPI (асинхронні роутери, DI, OpenAPI 3.1)
* **Telegram Bot:** `aiogram 3.x` (Long Polling у закритій мережі + фоновий `BRPOP` воркер черги Redis `queue:notifications:telegram`)
* **База даних:** PostgreSQL 16+ (первинні ключі **UUIDv7** за RFC 9562, патерн Single Table Inheritance для таблиці `reminders`, append-only для `exchange_rates`)
* **ORM та міграції:** SQLAlchemy 2.0 (`asyncio`, Declarative Base, `lazy="raise"`) + Alembic (`asyncpg`)
* **Черги та фонові задачі:** Redis 7+ та ARQ (щохвилинний Cron-полер із `FOR UPDATE SKIP LOCKED`, синхронізація курсів валют, дайджести)
* **Логування:** `Loguru` (консоль + ротація файлів у `logs/`)
* **Пакетний менеджер та інструменти:** `uv`, `ruff`, `mypy`, `pytest` (усі команди запускаються виключно через `uv run --directory backend ...`)

---

## 3. 🚫 17 Обов'язкових архітектурних інваріантів

1. **Сувора ізоляція модулів у Write-пайплайні (Modular Boundaries):**
   * Кожен бізнес-модуль у `backend/src/modules/<name>/` (`users`, `reminders`, `finance`) є автономним.
   * Прямий імпорт внутрішніх ORM-моделей, репозиторіїв або Use Cases з одного модуля в інший **категорично заборонений**:
     * ❌ `from src.modules.finance.infrastructure.models import ExchangeRateModel` (всередині `reminders`)
     * ✅ `from src.modules.finance.public import FinancePublicGateway`
   * *Виняток для Read Side:* `QueryService` має право виконувати оптимізовані SQL `SELECT / JOIN` для формування вихідних DTO.

2. **Rich Domain Model та заборона прямої мутації стану:**
   * Бізнес-логіка (перехід із тріалу в платний статус, списання акційного циклу знижки, розрахунок динамічного пріоритету, завершення курсу ліків) інкапсульована всередині методів доменних агрегатів (`subscription.record_payment()`, `medication.record_intake()`), а не розмазана по роутерах чи сервісах.
   * Усі агрегати наслідують `src.core.domain.AggregateRoot` (`BaseEntity`) та перевіряють активність через `self.ensure_active(...)` перед мутаціями.

3. **Single Table Inheritance (STI) у БД проти Чистих Агрегатів у Домені:**
   * На рівні PostgreSQL усі 5 типів нагадувань зберігаються в **єдиній таблиці `reminders`** (задля миттєвої вибірки шедулером за одним індексом `idx_reminders_scheduler`).
   * На рівні Python-коду заборонено створювати «божественний об'єкт» (God Object): `ReminderMapper` зобов'язаний трансформувати рядок таблиці `reminders` у відповідний доменний агрегат (`AnniversaryReminder`, `OpenTaskReminder`, `DeadlineTaskReminder`, `SubscriptionReminder`, `MedicationReminder`), а валідація допустимих пар `(reminder_type, schedule_logic)` виконується суворо за матрицею сумісності (`IncompatibleScheduleLogicError`).

4. **Безстатусна часова проекція для `lead_times` (Time-Series Projection):**
   * Категорично заборонено зберігати в БД числовий індекс поточного елемента масиву `lead_times` (`lead_time_index`).
   * Наступний момент спрацювання `next_trigger_at` завжди обчислюється детерміновано через проекцію часових зміщень від цільової дати події ($T_k = T_{\text{target}} - \text{offset}_k$) та вибір найменшої точки $T_k > T_{\text{current}}$.

5. **Обов'язкове `lazy="raise"` у SQLAlchemy:**
   * Усі зв'язки `relationship()` в ORM-моделях зобов'язані містити `lazy="raise"`, щоб унеможливити неявні I/O запити та проблему N+1.

6. **Прагматичний CQRS (`QueryService` тільки для читання):**
   * У класах `QueryService` (`queries/`) суворо заборонені будь-які операції зміни даних (`INSERT`, `UPDATE`, `DELETE`). Вони повертають виключно Pydantic DTO напряму з SQL-вибірок.

7. **Контроль транзакцій (`uow.commit()`):**
   * Викликати `await uow.commit()` дозволено **тільки кореневому (ініціюючому) Use Case / Application Service** (або функції фонової задачі ARQ). Репозиторії, мапери, роутери, хендлери бота та вкладені виклики `PublicGateway` з переданим зовнішнім `uow` ніколи не роблять коміт самостійно.

8. **Повна розв'язка Бекенду/Шедулера від Telegram SDK:**
   * Доменні модулі та воркери ARQ не імпортують `aiogram` і не викликають Telegram API напряму.
   * Готові сповіщення (`NotificationPayload`) публікуються у Redis-чергу (`LPUSH queue:notifications:telegram`), звідки їх вичитує `consumer.py` всередині сервісу бота через блокуючий `BRPOP`.

9. **Логування виключно через Loguru:**
   * Використовувати тільки `from loguru import logger` (через фасад `from src.core import logger`). Виклики `print()` або стандартного модуля `logging` заборонені.

10. **Семантика HTTP PUT vs PATCH:**
    * Усі `PUT`-запити реалізують виключно **Full Update** (передаються всі поля сутності; частковий перезапис через `exclude_unset=True` у PUT заборонений).
    * Точкові зміни окремих атрибутів виконуються через `PATCH` з окремим DTO, а переходи станів / дії користувача (`snooze`, `complete`, `record-intake`) — через окремі `POST` RPC-ендпоінти.

11. **Обов'язкове оптимістичне блокування (OCC) через `version`:**
    * Усі змінювані таблиці (`users`, `user_telegram_accounts`, `user_settings`, `reminders`, `medication_intake_logs`) містять поле `version: Mapped[int]` та `__mapper_args__ = {"version_id_col": version}`.
    * При одночасній зміні запису користувачем у боті та фоновим шедулером конфлікт версій (`StaleDataError`) перехоплюється і транслюється в `OptimisticLockConflictException` (`HTTP 409 Conflict`).

12. **Стандарт системних полів та UUIDv7:**
    * Усі первинні ключі (PK) у всіх таблицях — суворо **UUIDv7** (RFC 9562, монотонно зростаючі за часом).
    * Часові мітки в БД зберігаються виключно в UTC (`TIMESTAMPTZ`).
    * Поле `deleted_at: Mapped[datetime | None]` присутнє лише в сутностях із підтримкою Soft Delete (`users`, `reminders`, `medication_intake_logs`). У таблицях 1:1 (`user_settings`, `user_telegram_accounts`) та в append-only таблиці `exchange_rates` поле `deleted_at` відсутнє.

13. **Розподіл Soft Delete та Hard Delete:**
    * **Soft Delete** (`deleted_at = now_utc()`) використовується для приховування сутностей, які мають пов'язані реляційні дані чи історію, та виконується через `PATCH` / доменний метод `soft_delete()`. Усі активні вибірки та індекси шедулера обов'язково фільтрують `deleted_at IS NULL`.
    * **Hard Delete** (`DELETE FROM ...` з `ON DELETE CASCADE`) використовується для повного фізичного видалення даних (наприклад, `HTTP DELETE` при повному очищенні акаунта чи чернетки).

14. **Стандарти Pydantic v2 (`typing.Annotated`) та Конфігурації (`APP_CONFIG__`):**
    * Усі поля Pydantic-моделей та DTO з метаданими `Field()` описуються виключно через `typing.Annotated[T, Field(...)]`. Застарілий синтаксис `field: T = Field(...)` заборонений.
    * Усі змінні оточення конфігурації `pydantic-settings` мають префікс `APP_CONFIG__` із роздільником вкладеності `__`.

15. **Пакетні фасади (`__all__`) та Strict No-Proxy / SSOT:**
    * Публічний API підпакетів (`src/core`, `src/infrastructure/db`, `domain/`, `public.py`) експортується через `__init__.py` за допомогою явного списку `__all__`.
    * Категорично заборонено додавати `__all__` у внутрішні файли реалізації (`models.py`, `repository.py`, `mappers.py`).
    * При рефакторингу чи перенесенні коду заборонено залишати файли-прошарки або транзитні реекспорти «для сумісності» — усі споживачі одразу оновлюються на імпорт із нового канонічного місця.

16. **Ізоляція тестової бази даних (`reminder_app_test`) та Savepoint Rollback:**
    * Усі інтеграційні та API-тести виконуються виключно у виділеній тестовій БД `reminder_app_test` із транзакційним відкатом (`create_savepoint` + `rollback()` після кожного тесту). Запускати тести на робочій базі категорично заборонено.

17. **Виконання всіх команд виключно через `uv run`:**
    * Будь-які інструменти (`ruff`, `mypy`, `pytest`, `alembic`, `pre-commit`) викликаються в терміналі тільки через `uv run --directory backend <command>`.

---

## 4. 🧪 Чек-лист самоконтролю перед завершенням задачі

Перед фінальною відповіддю користувачу агент зобов'язаний перевірити:
- [ ] 1. Дотримано термінологію з `CONTEXT.md` та схему БД з `DATABASE.md` (UUIDv7, STI, без зайвих видалених колонок).
- [ ] 2. Відсутні заборонені міжмодульні імпорти у Write-пайплайні; взаємодія між модулями йде через `PublicGateway`.
- [ ] 3. Усі `relationship()` в ORM-моделях мають `lazy="raise"`, а змінювані моделі — `version_id_col` (OCC).
- [ ] 4. Запити шедулера та `QueryService` враховують `deleted_at IS NULL` та правильні статуси (`ACTIVE`, `TRIAL`).
- [ ] 5. Для ліків із `strict_schedule = True` реалізовано обхід вікна `QuietHoursWindow`.
- [ ] 6. Для курсів валют працює перевірка свіжості (> 48 годин) із автоматичним fallback на курс НБУ (`NBU`).
- [ ] 7. Усі Pydantic v2 DTO використовують `typing.Annotated[T, Field(...)]`.
- [ ] 8. Команда `uv run --directory backend ruff check .` повертає 0 помилок.
- [ ] 9. Команда `uv run --directory backend mypy src` повертає 0 помилок.
- [ ] 10. Усі юніт- та інтеграційні тести (`uv run --directory backend pytest`) успішно проходять.
