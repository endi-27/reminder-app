# Архітектура системи: Reminder App (Modular Monolith + CQRS)

Цей документ описує технічну архітектуру, взаємодію сервісів, обґрунтування вибору технологічного стека та структуру бекенду для персонального сервісу нагадувань.

---

## 1. Загальна схема системи (Container & Deployment View)

Усі компоненти розгортаються на одному VPS в єдиній ізольованій мережі **Docker Network**. Жоден сервіс (крім SSH) **не виставляє порти назовні**.

```mermaid
flowchart TD
    User([Користувач]) <-->|Telegram App| TGServers[Сервери Telegram API]
    
    subgraph Host["VPS / Server (Ізольована Docker Network)"]
        subgraph BotService["Bot Container (aiogram 3.x)"]
            TGBot[aiogram Polling Handler]
            NotifyConsumer[Notification Worker / Consumer]
        end

        subgraph BackendService["Backend Container (FastAPI)"]
            API[FastAPI REST API]
            QueryService[CQRS Read: Query Services]
            DomainWrite[CQRS Write: Domain + Repositories]
        end

        subgraph WorkerService["Background Tasks Container (ARQ)"]
            ARQCron[ARQ Cron & Scheduling]
            ARQTasks[Background Workers]
        end

        Postgres[(PostgreSQL 16)]
        Redis[(Redis 7)]
    end

    TGServers <-->|Long Polling (Вихідний HTTPS)| TGBot
    TGBot -->|HTTP REST Client (httpx)| API
    
    API -->|Async Read| Postgres
    API -->|Async Write / Units of Work| Postgres
    API -->|Enqueue Jobs| Redis
    
    ARQCron -->|Fetch due reminders| Postgres
    ARQTasks -->|HTTP Request| NBU[NBU API (Курси валют)]
    ARQTasks -->|Publish Notification Event| Redis
    
    Redis -->|Redis Stream / BRPOP| NotifyConsumer
    NotifyConsumer -->|Send Message| TGServers
```

---

## 2. Відповіді на ключові питання

### Питання 1: Чи потрібен патерн EDA (Event-Driven Architecture)?
**Відповідь: Повноцінний розподілений EDA (Event Sourcing / Kafka / Outbox pattern) тут надлишковий, АЛЕ потрібні легкі In-Memory події та асинхронні ARQ-задачі.**

* **Чому НЕ потрібен важкий EDA**:
  * Це персональний проєкт в межах **модульного моноліту**. 
  * Синхронний виклик через внутрішні фасади або `PublicGateway` між модулями набагато простіший у підтримці, типізації та налагодженні.
* **Де події потрібні**:
  * **Domain Events всередині агрегатів** (наприклад: `TaskCompleted`, `PriorityAutoEscalated`, `ReminderDue`). Вони публікуються в межах поточної транзакції для сайд-ефектів.
  * **Асинхронні задачі через ARQ**: коли задача завершилася, якщо це періодична підписка або річниця, створюється наступна дата або розраховується новий пріоритет.
* **Вердикт**: Чистий модульний моноліт з чіткими інтерфейсами між модулями + ARQ для асинхронних фонових задач — це ідеальний баланс надійності та простоти.

---

### Питання 2: Чи потрібен Nginx?
**Відповідь: На даному етапі — НІ, Nginx не потрібен.**

* **Причина**:
  * Твій бот працюватиме через **Long Polling** (`aiogram` сам ініціює вихідні HTTPS-запити до серверів Telegram). 
  * Бекенд (FastAPI), Redis і PostgreSQL живуть у закритій мережі Docker (`bridge` або custom network).
  * **Жодних публічних портів у світ не відкривається** (`ports: - "8000:8000"` у docker-compose прибираємо, залишаємо лише внутрішній резолв контейнерів).
* **Перевага**: Це **максимальна безпека "з коробки"**. Інтернет-сканери, боти і сканери портів навіть не побачать твій бекенд.
* **Коли Nginx знадобиться**:
  1. Якщо ти вирішиш перевести бота з Polling на Telegram Webhooks (тоді потрібен вхідний порт 443 і SSL-сертифікат).
  2. Якщо ти додаси Web UI (React/Vue/HTMX), доступний із браузера телефону.
  3. *Альтернатива Nginx для Web UI*: Замість публікації сайту в інтернет можна підняти безкоштовний **Tailscale / WireGuard** і мати доступ до бекенду через захищений персональний VPN взагалі без Nginx і доменів.

---

### Питання 3: Чи потрібен домен?
**Відповідь: НІ, домен не потрібен взагалі.**

* Бот зв'язується з Telegram API через звичайний клієнтський HTTPS-запит (так само як браузер відкриває сайти). Telegram знає твого бота за `BOT_TOKEN`, а не за доменом.
* Якщо тобі знадобиться локально відкрити FastAPI Swagger (`/docs`), ти можеш виконати одну команду:
  ```bash
  ssh -L 8000:localhost:8000 user@your-vps-ip
  ```
  І відкрити `http://localhost:8000/docs` прямо у своєму локальному браузері через безпечний SSH-тунель.

---

## 3. База даних: PostgreSQL vs MongoDB

| Критерій | PostgreSQL + async SQLAlchemy | MongoDB |
| :--- | :--- | :--- |
| **Споживання RAM** | **~30–50 MB** (чудово тюниться через `shared_buffers`) | **~300–800 MB+** (WiredTiger вимагає багато пам'яті за замовчуванням) |
| **Структура даних** | Дати, дедлайни, валюти, пріоритети — це **суворо структуровані** дані. Для специфічних налаштувань є нативний `JSONB`. | Документна модель підходить, але надлишкова. Немає строгих транзакцій без реплікації. |
| **Досвід розробника** | Твій основний стек, глибоке знання асинхронної SQLAlchemy. | Нова технологія, ризик помилок у транзакціях і зв'язках. |
| **Міграції** | Повний контроль через **Alembic**. | Ручний менеджмент схем або сторонні тулзи. |

**Вердикт**: Однозначно **PostgreSQL 16**. 
Думка про те, що нагадування — "неструктуровані", оманлива. Вони мають суворі інваріанти за часом, валютами та статусами. А поліморфні конфігурації повторень чудово зберігаються в колонці `extra_payload: JSONB`.

---

## 4. Зв'язок ARQ Cron $\rightarrow$ Telegram Bot (Відв'язка бекенда від Telegram)

Щоб зберегти чисту архітектуру і не додавати залежність від `aiogram` у бекенд/ARQ:

### Рекомендована схема: "Redis Delivery Queue (FIFO / Stream)"
1. **FastAPI / ARQ** нічого не знають про Telegram SDK. Вони знають лише про абстрактну сутність `NotificationMessage`:
   ```python
   # schema / event
   class NotificationPayload(BaseModel):
       recipient_channel: str = "telegram"
       recipient_id: str  # telegram user_id
       title: str
       body: str
       buttons: list[ActionButton] = []
   ```
2. Коли настав час нагадування, ARQ задача кладе подію в Redis-список або Redis Stream: `LPUSH queue:notifications:telegram <json>`.
3. У процесі **Bot Service** (поруч із Polling loop) запускається легкий фоновий таск `asyncio.create_task(notification_listener())`:
   * Він робить блокуюче читання: `BRPOP queue:notifications:telegram`.
   * Отримує повідомлення і надсилає його через `bot.send_message(..., reply_markup=...)`.
4. **Переваги**:
   * Бекенд на 100% абстрагований від Telegram.
   * Якщо бот тимчасово перезавантажується — повідомлення не губляться, вони чекають у черзі Redis.
   * Нуль зайвих процесів (споживач працює в тому ж event-loop, що й `aiogram`).

---

## 5. Внутрішня архітектура бекенду (Modular Monolith + CQRS)

```
src/
├── app/
│   ├── main.py                     # FastAPI composition root
│   ├── config.py                   # Pydantic v2 Settings
│   └── database.py                 # Async SQLAlchemy engine & session factory
│
├── modules/
│   ├── reminders/                  # Core Module: Tasks, Anniversaries, Subscriptions
│   │   ├── domain/                 # Чистий бізнес-код без залежностей
│   │   │   ├── models/             # Task, Anniversary, Subscription aggregates
│   │   │   ├── value_objects/      # Money, LeadTimes, RecurrencePattern, Priority
│   │   │   └── exceptions.py
│   │   ├── infrastructure/
│   │   │   ├── orm/                # SQLAlchemy models (declarative)
│   │   │   ├── mappers/            # ORM Model <-> Domain Entity mappers
│   │   │   └── repositories/       # Write repository implementations
│   │   ├── application/
│   │   │   ├── commands/           # Write use-cases (CreateTask, CompleteTask, etc.)
│   │   │   ├── queries/            # Read use-cases (Direct SQL/View projection -> DTO)
│   │   │   └── services/           # QueryService (Fast, bypasses domain aggregates)
│   │   └── presentation/
│   │       ├── api/                # FastAPI routers (v1 endpoints)
│   │       └── schemas/            # Pydantic v2 input/output schemas
│   │
│   ├── finance/                    # NBU rates & Currency Conversion
│   │   ├── domain/                 # ExchangeRate, Currency
│   │   ├── infrastructure/         # NBU Client (httpx), Redis Rate Cache
│   │   └── application/            # GetExchangeRateQuery
│   │
│   └── notifications/              # Dispatching & Scheduling
│       ├── domain/                 # QuietHoursPolicy, NotificationMessage
│       ├── infrastructure/         # RedisQueuePublisher
│       └── application/            # DispatchReminderCommand
│
└── workers/                        # ARQ Worker & Cron definitions
    ├── worker.py                   # ARQ Worker settings & cron functions
    └── tasks/                      # cron_check_due_reminders, cron_sync_nbu_rates
```

---

## 6. Баланс ресурсів (RAM Budget на хостингу)

Завдяки підібраному стеку проєкт буде екстремально легким:
* **PostgreSQL 16**: ~45 MB
* **Redis 7 (Alpine)**: ~15 MB
* **FastAPI Backend (Uvicorn)**: ~55 MB
* **ARQ Worker**: ~40 MB
* **aiogram 3.x Bot**: ~45 MB
* **Загальне споживання RAM**: **~200 MB**!

Він буде спокійно працювати навіть на найдешевшому VPS за $3/місяць (1 vCPU, 512MB–1GB RAM).

---

## 7. Чого не вистачало і що критично додати

1. **Alembic Migrations**: Обов'язково налаштувати з першого дня для безпечної еволюції схеми БД.
2. **Graceful Shutdown**: Обробка `SIGTERM` у боті та бекенді, щоб не обривати збереження транзакцій під час `docker compose restart`.
3. **Healthcheck endpoints**: У FastAPI додати `/healthz`, щоб Docker бачив стан готовності сервісу перед запуском бота.
4. **Structured JSON Logging**: Логування помилок у JSON-форматі для зручного читання через `docker compose logs`.
