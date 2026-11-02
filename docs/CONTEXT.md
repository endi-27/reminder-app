# Ubiquitous Language (Reminder Domain)

## Core Concepts & Terms

### User, UserTelegramAccount & UserSettings
The decoupled identity model of the system:
* **User**: Core account identity (`id: UUIDv7`, `username: str`, `role: SUPER_ADMIN | ADMIN | USER`, optional `password_hash` for Web/API dashboard access). Multi-tenant isolation is anchored on `user_id`.
* **UserTelegramAccount**: 1:1 decoupled messenger link (`telegram_id`, `telegram_chat_id`, `tg_username`, `tg_full_name`), isolating core user identity from the communication channel.
* **UserSettings**: 1:1 user preferences storing timezone (e.g. `Europe/Kyiv`), preferred exchange rate bank (`preferred_bank`), quiet hours window, and the `auto_deadline_priority_escalation` toggle (default: `True`).

### UUID v7 Primary Keys
All primary keys across the database strictly use **UUID v7** (RFC 9562). With an embedded 48-bit millisecond timestamp, UUID v7 provides monotonic time-ordering, preventing PostgreSQL B-tree index fragmentation while ensuring global distributed uniqueness.

### Soft Delete, Hard Delete & Optimistic Concurrency Control (OCC)
The system supports two complementary deletion strategies:
* **Soft Delete**: Sets `deleted_at: datetime = NOW()`. Used to hide or deactivate entities that have interconnected relational dependencies (e.g. intake logs, historical alerts) without breaking data integrity or losing context.
* **Hard Delete**: Executes physical SQL `DELETE` with `ON DELETE CASCADE`. Used when a user explicitly requests complete account removal, permanent erasure of drafts, or during administrative data purges.
All mutable entities also include an integer `version` field incremented on each update to prevent race conditions (Optimistic Concurrency Control) between user UI actions and background schedulers.

### Append-Only Exchange Rate Ledger
Exchange rates are stored in an append-only time-series ledger (`exchange_rates`), appending a new snapshot on every scrape rather than overwriting existing records. This retains local historical exchange rate trends for retrospective analysis while enabling instant lookups of the latest rate via `created_at DESC LIMIT 1`.

### Reminder
A core domain concept representing a future event, task, obligation, or medical intake that a specific user needs to be notified about.

### Reminder Type (ReminderType)
System-wide enum categorizing the domain nature of a reminder: `ANNIVERSARY`, `OPEN_TASK`, `DEADLINE_TASK`, `SUBSCRIPTION`, `MEDICATION`. Each type restricts which schedule logic types it permits.

### Schedule Logic Type (ScheduleLogicType)
System-wide enum defining the temporal calculation algorithm: `DATE_WITH_MONTH_INTERVAL`, `DAILY_AT_TIMES`, `EXACT_DATETIME_DEADLINE`, `EXACT_DATE_DEADLINE`, `INTERVAL_DAYS`, `INTERVAL_HOURS`.

### Unified Reminders Persistence (Single Table Inheritance)
Architectural pattern where all reminder types are stored in a single unified `reminders` database table discriminated by `reminder_type` and `schedule_logic`. This enables ultra-fast single-index scheduler queries while preserving clean, distinct DDD aggregates with type-specific invariants in the backend.

### Anniversary
An annually recurring calendar event tied to a specific day and month (e.g., birthday, memorial date) with early cascade alerts (14, 7, 3, 1, 0 days). Handles leap-year semantics (Feb 29).

### Open Task
A task without a rigid deadline intended for passive nudges or periodic daily digests to prevent abandonment and notification fatigue. May optionally have an explicit priority (Low, Medium, High, Critical) or be Unset.

### Deadline Task
A task bound to a concrete expiration datetime or date (`due_date` / `due_datetime`) with priority-driven or time-escalated alert frequencies. May have an explicit priority or rely on dynamic calculation.

### Dynamic Priority
An automatically escalating urgency tier (Low -> Medium -> High -> Critical) computed from the fraction of remaining time until the task's deadline. Applied only to Deadline Tasks that have no explicit priority (`UNSET`), provided the user has `auto_deadline_priority_escalation = True`.

### Subscription & Recurring Payment
A recurring financial obligation denominated in a specific currency with a predefined billing cadence (day-of-month or fixed-day intervals) and advance payment warnings.

### Trial Subscription
A subscription that starts in a free or discounted trial period expiring on `trial_end_date`. It triggers early warning reminders (e.g., 5, 3, 1 days prior) detailing the upcoming regular charge, with an automatic lifecycle transition into a standard paid subscription if not cancelled.

### Promotional Discount (Introductory Pricing)
A temporary pricing tier for subscriptions where a discounted rate applies for a specified number of billing cycles (e.g., $1.99/mo for the first 3 cycles, then $9.99/mo). Tracks remaining discounted cycles, notifies the user when the discount period is ending, and automatically transitions to the full regular price.

### Medication Reminder (Medication Course)
A time-bound or ongoing medical intake schedule characterized by course duration (number of days), intake cadence (fixed daily hours or strict hourly intervals), and adherence tracking (doses taken/missed).

### Strict Schedule (Quiet Hours Override)
A flag (primarily for critical medications like antibiotics) indicating that a reminder must never be postponed by Quiet Hours and must fire precisely on time.

### Lead Time & Custom Dynamic Intervals (Time-Series Projection)
The predefined or user-configured temporal offsets before an event's target date ($T_{\text{target}}$, e.g. 14 days, 3 days, 1 hour before). The scheduling engine projects these offsets into a sorted timeline of absolute timestamps ($T_k = T_{\text{target}} - \text{offset}_k$) and advances statelessly by finding the next timestamp $T > T_{\text{current}}$, completely eliminating fragile array index tracking and gracefully accommodating dynamic user edits.

### End of Month Policy (EndOfMonthPolicy)
A resolution strategy for calendar recurrence (Logic 1) when a target day does not exist in a given month (e.g. 29 Feb in non-leap years, or 31 in 30-day months). Configurable via enum: `LAST_DAY_OF_MONTH` (default: adjusts to 28/29 Feb, 30 Apr) or `FIRST_DAY_OF_NEXT_MONTH` (adjusts to 1 Mar, 1 May).

### Quiet Hours
A user-configured time window (e.g., 23:00 to 08:00 in the user's timezone) during which standard push alerts are silenced or held back until morning, unless explicitly bypassed by a `strict_schedule`.

### Exchange Rate Providers & Fallback Policy
Financial rate sources (NBU, Monobank, PrivatBank) fetched by daily cron. Users select their `preferred_bank`. If the chosen commercial bank rate is stale (>48 hours), the system falls back to the official NBU rate (Priority 1) with an explicit explanatory note in the notification.
