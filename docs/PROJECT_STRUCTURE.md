# Структура проєкту та керівництво зі створення модулів (Project Structure & Module Guide)

Цей документ визначає фізичну організацію вихідного коду сервісу **Reminder App**, описує призначення системних пакетів та надає архітектурні шаблони для розробки бізнес-модулів, фонових задач ARQ і Telegram-бота.

---

## 1. Загальна файлова структура репозиторію

```
reminder-app/
├── .env                                 # Локальні змінні оточення (секрети, доступи до БД, токен бота)
├── .env.example                         # Шаблон змінних оточення для розгортання
├── docker-compose.yaml                  # Оркестрація: postgres, redis, backend, worker, bot, db_backup
├── .gitignore                           # Глобальний ігнор (Python, logs, backups, .env)
├── .dockerignore                        # Глобальний dockerignore
│
├── AGENTS.md                            # Єдина конституція та інваріанти для AI-агентів
├── CONTRIBUTING.md                      # Стандарти Git (Conventional Commits, гілки, pre-commit)
├── README.md                            # Огляд проєкту, швидкий старт та команди розробки
│
├── docs/                                # Системна та архітектурна документація (Single Source of Truth)
│   ├── CONTEXT.md                       # Глосарій домену (Ubiquitous Language — SSOT термінів)
│   ├── SPECIFICATION.md                 # Бізнес-вимоги, DDD-модель та логіка планування
│   ├── ARCHITECTURE.md                  # Системна архітектура, пайплайн доставки та ARQ крони
│   ├── DATABASE.md                      # Схема БД PostgreSQL 16, ER-діаграма, DDL та приклади JSONB
│   └── PROJECT_STRUCTURE.md             # Поточний документ: структура каталогів та шаблони модулів
│
├── .agents/                             # Конфігурація та правила для AI-асистентів
│   └── rules/
│       └── backend.md                   # Обов'язковий регламент самоконтролю для backend/**
│
├── backups/                             # Резервні копії БД PostgreSQL (.sql, .dump) [.keep]
├── logs/                                # Логи сервісів з ротацією Loguru
│   ├── app/                             # Логи FastAPI додатку (app.log) [.keep]
│   ├── worker/                          # Логи ARQ воркера та шедулера (worker.log) [.keep]
│   ├── bot/                             # Логи Telegram-бота (bot.log) [.keep]
│   └── backups/                         # Логи бекапів БД (backup.log) [.keep]
├── scripts/                             # Допоміжні скрипти (pg_backup_rotated.sh, entrypoint.sh) [.keep]
│
└── backend/                             # ⚙️ ОСНОВНИЙ ПРОСТІР КОДУ (Python 3.12+, FastAPI, aiogram, ARQ)
    ├── pyproject.toml                   # Залежності та конфігурація інструментів (uv, ruff, mypy, pytest)
    ├── Dockerfile                       # Єдина мультистейдж збірка для API, ARQ Worker та Telegram Bot
    │
    ├── alembic/                         # Міграції схеми бази даних (Alembic + asyncpg)
    │   ├── versions/                    # Версії міграцій (SQL/DDL зміни) [.keep]
    │   └── env.py                       # Асинхронний конфіг Alembic з реєстрацією ORM-моделей
    │
    ├── tests/                           # Багаторівневі автотести (pytest + pytest-asyncio)
    │   ├── unit/                        # Швидкі тести домену, Time-Series розрахунків та Use Cases з FakeUoW [.keep]
    │   ├── integration/                 # Тести з реальною тестовою БД (reminder_app_test) та Redis [.keep]
    │   └── api/                         # E2E / API тести HTTP роутерів (httpx.AsyncClient) [.keep]
    │
    └── src/                             # Вихідний код системи
        ├── api/                         # HTTP презентаційний шар (FastAPI main.py, Routers, Schemas, DI)
        ├── bot/                         # Telegram Bot сервіс (bot.py фабрика, main.py раннер, Redis Consumer)
        ├── tasks/                       # Фоновий воркер та Cron-шедулер (ARQ worker.py)
        ├── modules/                     # ДОМЕННІ МОДУЛІ БІЗНЕСУ (Модульний моноліт: users, reminders, finance)
        ├── infrastructure/              # Інфраструктурні адаптери (SQLAlchemy Base, UoW, Redis, Mappers)
        └── core/                        # Ядро системи (чисті конфігурації, протоколи, базовий домен)
```

---

## 2. Огляд спільних системних пакетів (`backend/src/`)

> [!IMPORTANT]
> **Стандарт пакетних фасадів та імпортів**: Усі підпакети реалізуються як **пакетні фасади** з явним списком експортів `__all__` у файлах `__init__.py`. Зовнішній код імпортує сутності виключно з кореня пакетів (наприклад: `from src.core import settings, logger`, `from src.infrastructure.db import Base, SqlAlchemyUnitOfWork`). Глибокі імпорти з внутрішніх файлів реалізації заборонені.

### 2.1. `src/core/` — Ядро системи (Незалежне від бізнес-модулів)
* `__init__.py`: Публічний фасад ядра (`__all__`).
* `domain/`: Канонічні базові класи чистого домену:
  * `base.py`: `BaseEntity` (ідентифікатор **UUIDv7** за RFC 9562, системні мітки `created_at`, `updated_at`).
  * `aggregate.py`: `AggregateRoot` (успадковує `BaseEntity`, додає `version` для OCC, опціональний `deleted_at`, методи `soft_delete()`, `restore()`, властивість `is_active` та перевірку інваріантів `ensure_active()`).
* `config.py`: Типізовані налаштування `pydantic-settings` (`Settings` з префіксом `APP_CONFIG__` та роздільником `__`).
* `database.py`: Ініціалізація `create_async_engine` та фабрики сесій `async_sessionmaker`.
* `redis.py`: Пул підключень до Redis 7+ (для черг сповіщень, ARQ та кешування).
* `security.py`: Утиліти хешування паролів (`IPasswordHasher`, `BcryptPasswordHasher`) та перевірки токенів для REST API.
* `logger.py`: Конфігурація структурованого логування `Loguru` (консоль + ротація файлів).
* `exceptions.py`: Базова ієрархія архітектурних винятків (`AppException`, `NotFoundException`, `ConflictException`, `OptimisticLockConflictException`, `DomainException`, `IncompatibleScheduleLogicError`, `InactiveEntityError`).
* `protocols.py`: Системні протоколи `typing.Protocol` (`IUnitOfWork`, `IEventBus`, `INotificationPublisher`, `IPasswordHasher`).
* `events/`: Внутрішньопроцесна шина доменних подій (`BaseEvent`, `AsyncEventBus`).

---

### 2.2. `src/infrastructure/` — Інфраструктурні адаптери
* `db/`: Пакет взаємодії з PostgreSQL 16+:
  * `__init__.py`: Експортує `Base`, `SqlAlchemyUnitOfWork`, `SqlAlchemyBaseCrudRepository`, `SqlAlchemyBaseReadRepository`, `BaseMapper` та ORM-міксіни.
  * `base.py`: `DeclarativeBase` із правилами найменування ключів/індексів (`naming_convention`) та модульні міксіни:
    * `UUIDPrimaryKeyMixin` (UUIDv7)
    * `TimestampMixin` (`created_at`, `updated_at`)
    * `SoftDeleteMixin` (`deleted_at`)
    * `VersionedMixin` (`version` + `version_id_col` для автоматичного OCC в SQLAlchemy)
  * `uow.py`: `SqlAlchemyUnitOfWork` (підтримує Request-Scoped режим для HTTP/Bot запитів та Self-Contained режим для фонових задач ARQ).
  * `repositories.py`: Базові узагальнені репозиторії `SqlAlchemyBaseCrudRepository[TDomain, TModel]`.
  * `mappers.py`: Абстрактний `BaseMapper[TDomain, TModel]` для двосторонньої трансформації між чистим доменом та ORM.
* `notifications/`: Інфраструктура доставки сповіщень у бот:
  * `redis_queue_publisher.py`: Реалізує `INotificationPublisher` — публікує `NotificationPayload` у список Redis (`LPUSH queue:notifications:telegram`).

---

### 2.3. `src/api/` — HTTP Презентаційний шар (FastAPI)
* `__init__.py`: Публічний фасад презентаційного шару (експортує `app`, `create_app` та DI залежності).
* `main.py`: Точка входу FastAPI додатку (`create_app`, `lifespan`, роутери, запуск через Uvicorn).
* `dependencies.py`: Глобальні FastAPI `Depends`-провайдери (`get_uow`, `get_current_user`, `require_role`).
* `middlewares.py`: HTTP-мідлвари (CORS, Request Context Logger для Loguru).
* `exception_handlers.py`: Глобальна трансляція доменних та інфраструктурних винятків у стандартизовані HTTP JSON-відповіді (зокрема `StaleDataError` / `OptimisticLockConflictException` $\rightarrow$ `HTTP 409 Conflict`).
* `schemas/`: Стандартизовані Pydantic v2 схеми (`PaginationParams`, `PaginatedResponse`, `OCCVersionDTO`).
* `v1/`:
  * `router.py`: Кореневий роутер `/api/v1`, що об'єднує роутери модулів (`users`, `reminders`, `finance`) та `/health`.

---

### 2.4. `src/tasks/` — Фоновий воркер та Cron-шедулер (ARQ)
* `__init__.py`: Експортує `WorkerSettings`, `TaskDispatcher`.
* `worker.py`: Налаштування життєвого циклу воркера (`startup`, `shutdown`, ініціалізація сесій БД та клієнтів банків).
* `dispatcher.py`: `TaskDispatcher` для постановки фонових задач із коду додатку.
* `cron.py`: Реєстрація періодичних задач:
  * `cron_check_due_reminders` (кожні 60 секунд — вибірка `FOR UPDATE SKIP LOCKED`, перевірка Quiet Hours, розрахунок Time-Series Projection).
  * `cron_sync_exchange_rates` (кожні 6 годин — збір курсів НБУ, Monobank, ПриватБанк).
  * `cron_daily_task_digest` (формування дайджестів відкритих задач).
  * `cron_check_expiring_trials_and_discounts` (перевірка завершення тріалів та акційних циклів).
* `functions/`: Реалізація функцій-виконувачів фонових завдань.

---

### 2.5. `src/bot/` — Сервіс Telegram-бота (aiogram 3.x)
* `bot.py`: Фабрика компонентів Telegram-бота (`BOT_COMMANDS`, `create_bot`, `create_dispatcher`).
* `main.py`: Точка входу сервісу бота (запуск `run_bot()` у режимі Long Polling + запуск фонового споживача черги Redis).
* `consumer.py`: Асинхронний воркер доставки (`BRPOP queue:notifications:telegram`), який десеріалізує `NotificationPayload`, форматує HTML та надсилає повідомлення з інлайн-кнопками в Telegram.
* `client/`:
  * `api_client.py`: Внутрішній асинхронний HTTP-клієнт `BackendApiClient` (`httpx.AsyncClient`) з автентифікацією через `X-Internal-Token` + `X-Telegram-Id`.
  * `exceptions.py`: Клієнтські винятки бекенду (`BotApiError`, `BotApiNotFoundError`, `BotApiConflictError`, `BotApiValidationError`).
* `callbacks/`:
  * `data.py`: Суворо типізовані фабрики `CallbackData` (`ReminderActionCallback`, `ReminderListFilterCallback`, `ReminderDetailCallback`, `CreateReminderTypeCallback`, `CreateWizardCallback`, `SettingsCallback`) із дотриманням ліміту Telegram `<= 64 bytes`.
* `states/`:
  * `reminder_create.py`: FSM-стани покрокових майстрів створення нагадувань для 5 типів.
  * `settings_edit.py`: FSM-стани редагування персональних налаштувань користувача.
* `formatters/`:
  * `messages.py`: Чисті функції генерації безпечного HTML-розмітки (`format_notification_payload`, `format_reminder_detail_message`, `format_rates_message`, `format_settings_message`) із переводом часу в таймзону користувача.
* `keyboards/`:
  * `reply.py`: Головне меню 2x2 та клавіатура швидкого скасування дій.
  * `inline_reminders.py`: Інлайн-клавіатури категорій, фільтрів, пагінації, карток дій та сповіщень.
  * `inline_settings.py`: Інлайн-клавіатури вибору банку, таймзони, тихих годин та ескалації дедлайнів.
* `middlewares/`:
  * `auth.py`: `BotAuthMiddleware` — синхронізація профілю користувача за `telegram_id` через бекенд та інжекція `current_user` і `api_client`.
  * `logging.py`: `BotLoggingMiddleware` — логування подій Telegram через `Loguru`.
* `handlers/`:
  * `start.py`: Команди `/start`, `/help`, `/cancel` та швидке скасування FSM.
  * `settings.py`: Меню перегляду та інтерактивної зміни персональних налаштувань.
  * `finance.py`: Зведення актуальних курсів валют банків за командою `/rates`.
  * `reminders_list.py`: Перегляд нагадувань за категоріями, пагінація, деталі, статистика ліків, пауза та видалення.
  * `reminders_actions.py`: Обробка натискань кнопок під сповіщеннями (`[💊 Прийняв]`, `[⏰ +15 хв]`, `[💳 Оплачено]`, `[❌ Скасував тріал]`, `[✅ Виконано]`) з редагуванням повідомлення на місці.
  * `reminders_create.py`: 5 інтерактивних FSM-майстрів створення всіх типів нагадувань.
  * `errors.py`: Глобальний обробник неперехоплених помилок бота.

---

## 3. Структура бізнес-модулів (`backend/src/modules/`)

Кожен модуль у `src/modules/` будується як ізольований вертикальний зріз із чітким поділом на **Write Side** (Domain + Application) та **Read Side** (Queries — прагматичний CQRS).

### 3.1. Модуль `reminders` (Комплексний модуль із Single Table Inheritance)

Поєднує **єдину фізичну таблицю `reminders` у БД** (для максимальної швидкості шедулера) та **5 окремих чистих доменних агрегатів у Python**:

```
backend/src/modules/reminders/
├── __init__.py
├── domain/                          # 1. ЧИСТИЙ ДОМЕН (Жодних імпортів SQLAlchemy чи FastAPI)
│   ├── __init__.py                  # Фасад домену (__all__)
│   ├── enums.py                     # ReminderType, ScheduleLogicType, ReminderStatus, Priority, EndOfMonthPolicy
│   ├── value_objects.py             # Money, LeadTimes, RecurrencePattern (6 схем розкладу)
│   ├── aggregates/                  # 5 окремих агрегатів (успадковують AggregateRoot)
│   │   ├── __init__.py
│   │   ├── anniversary.py           # AnniversaryReminder
│   │   ├── open_task.py             # OpenTaskReminder
│   │   ├── deadline_task.py         # DeadlineTaskReminder (динамічний пріоритет)
│   │   ├── subscription.py          # SubscriptionReminder (тріали + акційні цикли)
│   │   └── medication.py            # MedicationReminder (курси, strict_schedule, логи прийому)
│   ├── services/
│   │   └── schedule_calculator.py   # Детермінований розрахунок next_trigger_at (Time-Series Projection)
│   ├── exceptions.py                # IncompatibleScheduleLogicError, InvalidDiscountCycleError
│   ├── events.py                    # ReminderTriggeredEvent, TrialConvertedEvent, MedicationTakenEvent
│   └── interfaces.py                # IReminderRepository, IMedicationLogRepository (typing.Protocol)
│
├── application/                     # 2. WRITE SIDE (Команди та оркестрація транзакцій)
│   ├── __init__.py
│   ├── dto.py                       # Command DTO (CreateReminderDTO, RecordActionDTO, SnoozeDTO)
│   └── use_cases/
│       ├── create_reminder.py       # Створення + первинний розрахунок next_trigger_at
│       ├── process_due_reminders.py # Обробка пачки шедулера, збагачення курсом, постановка в чергу
│       ├── handle_action.py         # Обробка інлайн-кнопок (Оплачено, Прийняв, Відкласти, Виконано)
│       └── update_reminder.py       # Редагування з перерахунком Time-Series та перевіркою OCC version
│
├── queries/                         # 3. READ SIDE (Прагматичний CQRS — швидкі SELECT у DTO)
│   ├── __init__.py
│   ├── dto.py                       # ReminderListItemDTO, ReminderDetailDTO, AdherenceReportDTO
│   └── query_service.py             # ReminderQueryService (фільтри за user_id, типом, статусом)
│
├── infrastructure/                  # 4. ІНФРАСТРУКТУРА ЗБЕРЕЖЕННЯ (STI Persistence)
│   ├── __init__.py
│   ├── models.py                    # ReminderModel (таблиця reminders), MedicationIntakeLogModel (lazy="raise")
│   ├── mappers.py                   # Поліморфний ReminderMapper (ReminderModel <-> конкретний AggregateRoot)
│   └── repository.py                # SqlAlchemyReminderRepository (зокрема SELECT ... FOR UPDATE SKIP LOCKED)
│
├── public.py                        # 5. ПУБЛІЧНИЙ ШЛЮЗ (RemindersPublicGateway з __all__)
├── dependencies.py                  # 6. DI провайдери модуля
└── router.py                        # 7. HTTP РОУТЕР (/api/v1/reminders)
```

---

### 3.2. Модуль `users` (Декомпонований профіль та налаштування)

```
backend/src/modules/users/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── enums.py                     # UserRole (SUPER_ADMIN, ADMIN, USER)
│   ├── models.py                    # User (AggregateRoot), UserTelegramAccount, UserSettings
│   ├── exceptions.py
│   └── interfaces.py                # IUserRepository (typing.Protocol)
├── application/
│   ├── __init__.py
│   ├── dto.py                       # RegisterTelegramUserDTO, UpdateUserSettingsDTO
│   └── use_cases/                   # GetOrCreateTelegramUserUseCase, UpdateSettingsUseCase
├── queries/
│   ├── __init__.py
│   ├── dto.py                       # UserProfileDTO, UserSettingsDTO
│   └── query_service.py             # UserQueryService
├── infrastructure/
│   ├── __init__.py
│   ├── models.py                    # UserModel, UserTelegramAccountModel, UserSettingsModel (1:1, lazy="raise")
│   ├── mappers.py                   # UserMapper
│   └── repository.py                # SqlAlchemyUserRepository
├── public.py                        # UsersPublicGateway (отримання налаштувань/таймзони для шедулера та бота)
├── dependencies.py
└── router.py                        # HTTP РОУТЕР (/api/v1/users)
```

---

### 3.3. Модуль `finance` (Курси валют та Fallback-політика)

```
backend/src/modules/finance/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── enums.py                     # ExchangeRateProvider (NBU, MONOBANK, PRIVATBANK)
│   ├── models.py                    # ExchangeRate, ConversionResult (із прапорцем is_stale_fallback)
│   └── interfaces.py                # IExchangeRateRepository, IBankRateProviderClient
├── application/
│   ├── __init__.py
│   ├── dto.py
│   └── services/
│       ├── rate_sync_service.py     # Збір курсів із банків та append-only запис у БД
│       └── currency_converter.py    # Конвертація з перевіркою свіжості (>48h -> фолбек на НБУ)
├── queries/
│   ├── __init__.py
│   ├── dto.py                       # RateHistoryDTO, LatestRatesDTO
│   └── query_service.py             # FinanceQueryService (історія курсів та поточні значення)
├── infrastructure/
│   ├── __init__.py
│   ├── models.py                    # ExchangeRateModel (Append-Only таблиця exchange_rates)
│   ├── mappers.py
│   ├── repository.py                # SqlAlchemyExchangeRateRepository
│   └── clients/                     # HTTP-клієнти банків (httpx)
│       ├── nbu_client.py            # Пріоритет 1 (Золотий стандарт)
│       ├── monobank_client.py       # Картковий курс (із захистом від rate-limit 60s)
│       └── privatbank_client.py     # Картковий курс ПриватБанку
├── public.py                        # FinancePublicGateway (метод convert_to_uah для модуля reminders)
├── dependencies.py
└── router.py                        # HTTP РОУТЕР (/api/v1/finance)
```

---

## 4. Чек-лист створення або розширення модуля

1. Описати чисті доменні моделі, Value Objects та протоколи репозиторіїв у `domain/` (використовуючи `typing.Protocol`).
2. Налаштувати ORM-моделі в `infrastructure/models.py` з використанням базових міксінів (`UUIDPrimaryKeyMixin`, `TimestampMixin`, `VersionedMixin`, за потреби `SoftDeleteMixin`) та обов'язковим `lazy="raise"` на всіх зв'язках.
3. Реалізувати мапер (`infrastructure/mappers.py`) та репозиторій (`infrastructure/repository.py`).
4. Створити Use Cases у `application/` (контроль транзакції `async with uow:` та `await uow.commit()` виключно на рівні Use Case).
5. Описати Pydantic v2 DTO з використанням `typing.Annotated[T, Field(...)]`.
6. Реалізувати `QueryService` у `queries/` для операцій читання (з фільтрацією `deleted_at IS NULL`).
7. Експортувати міжмодульний інтерфейс через `public.py` (`PublicGateway` зі списком `__all__`).
8. Зареєструвати моделі в `backend/alembic/env.py` та створити міграцію.
9. Написати швидкі юніт-тести в `backend/tests/unit/` та інтеграційні тести в `backend/tests/integration/`.
