# Ubiquitous Language (Reminder Domain)

## Terms

### Reminder
A core domain concept representing a future event, task, or recurring obligation that the user needs to be notified about.

### Anniversary
An annually recurring calendar event tied to a specific day and month (e.g., birthday, memorial date) with early cascade alerts (14, 7, 3, 1, 0 days).

### Open Task
A task without a rigid deadline intended for passive nudges or periodic daily digests to prevent abandonment.

### Deadline Task
A task bound to a concrete expiration datetime (`due_date`) with priority-driven or time-escalated alert frequencies.

### Dynamic Priority
An automatically escalating urgency tier (Low -> Medium -> High -> Critical) computed from the fraction of remaining time until the task's deadline.

### Subscription
A recurring financial obligation denominated in a specific currency with predefined billing cadence (day-of-month or fixed-day intervals) and advance payment warnings.

### Lead Time
The predefined duration before an event's target date at which an advance notification should be sent (e.g., 3 days before payment).

### Quiet Hours
A user-configured time window during which push alerts are silenced or held back until the morning.

### NBU Exchange Rate
The official currency exchange rate provided by the National Bank of Ukraine API, used to compute Ukrainian Hryvnia (UAH) equivalents for foreign currency amounts.
