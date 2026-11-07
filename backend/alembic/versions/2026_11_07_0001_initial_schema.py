"""Канонічна початкова схема БД (PostgreSQL 16).

Revision ID: 2026_11_07_0001
Revises: None
Create Date: 2026-11-07 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_11_07_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Створення повного набору розширень, функцій, перелічень, таблиць та індексів."""
    # 1. Розширення pgcrypto
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    # 2. PL/pgSQL функція генерації UUID v7 у PostgreSQL 16 (RFC 9562)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION uuid_generate_v7() RETURNS UUID AS $$
        DECLARE
            v_time DOUBLE PRECISION;
            v_epoch_ms BIGINT;
            v_bytes BYTEA;
        BEGIN
            v_time := clock_timestamp();
            v_epoch_ms := TRUNC(EXTRACT(EPOCH FROM v_time) * 1000)::BIGINT;

            v_bytes := SUBSTRING(int8send(v_epoch_ms) FROM 3 FOR 6) || gen_random_bytes(10);

            v_bytes := SET_BYTE(v_bytes, 6, (GET_BYTE(v_bytes, 6) & 15) | 112);
            v_bytes := SET_BYTE(v_bytes, 8, (GET_BYTE(v_bytes, 8) & 63) | 128);

            RETURN encode(v_bytes, 'hex')::UUID;
        END;
        $$ LANGUAGE plpgsql VOLATILE;
        """
    )

    # 3. Створення типів перелічень (ENUMs)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role_enum') THEN
                CREATE TYPE user_role_enum AS ENUM ('SUPER_ADMIN', 'ADMIN', 'USER');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_type_enum') THEN
                CREATE TYPE reminder_type_enum AS ENUM ('ANNIVERSARY', 'OPEN_TASK', 'DEADLINE_TASK', 'SUBSCRIPTION', 'MEDICATION');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'schedule_logic_type_enum') THEN
                CREATE TYPE schedule_logic_type_enum AS ENUM (
                    'DATE_WITH_MONTH_INTERVAL',
                    'DAILY_AT_TIMES',
                    'EXACT_DATETIME_DEADLINE',
                    'EXACT_DATE_DEADLINE',
                    'INTERVAL_DAYS',
                    'INTERVAL_HOURS'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_status_enum') THEN
                CREATE TYPE reminder_status_enum AS ENUM ('ACTIVE', 'TRIAL', 'COMPLETED', 'PAUSED', 'CANCELLED');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'priority_enum') THEN
                CREATE TYPE priority_enum AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'exchange_rate_provider_enum') THEN
                CREATE TYPE exchange_rate_provider_enum AS ENUM ('NBU', 'MONOBANK', 'PRIVATBANK');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'end_of_month_policy_enum') THEN
                CREATE TYPE end_of_month_policy_enum AS ENUM ('LAST_DAY_OF_MONTH', 'FIRST_DAY_OF_NEXT_MONTH');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'medication_log_status_enum') THEN
                CREATE TYPE medication_log_status_enum AS ENUM ('TAKEN', 'SNOOZED', 'MISSED');
            END IF;
        END $$;
        """
    )

    # 4. Таблиця USERS
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            username VARCHAR(255) NOT NULL UNIQUE,
            role user_role_enum NOT NULL DEFAULT 'USER',
            password_hash VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ,
            version INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # 5. Таблиця USER_TELEGRAM_ACCOUNTS (1:1)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_telegram_accounts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL UNIQUE,
            telegram_chat_id BIGINT NOT NULL UNIQUE,
            tg_username VARCHAR(255),
            tg_full_name VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            version INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # 6. Таблиця USER_SETTINGS (1:1)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Kyiv',
            quiet_hours_start TIME NOT NULL DEFAULT '23:00:00',
            quiet_hours_end TIME NOT NULL DEFAULT '08:00:00',
            preferred_bank exchange_rate_provider_enum NOT NULL DEFAULT 'MONOBANK',
            auto_deadline_priority_escalation BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            version INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    # 7. Таблиця REMINDERS (Single Table Inheritance)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reminder_type reminder_type_enum NOT NULL,
            schedule_logic schedule_logic_type_enum NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            status reminder_status_enum NOT NULL DEFAULT 'ACTIVE',
            next_trigger_at TIMESTAMPTZ NOT NULL,
            schedule_config JSONB NOT NULL,
            lead_times JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ,
            version INTEGER NOT NULL DEFAULT 1,

            due_datetime TIMESTAMPTZ,
            base_priority priority_enum,
            calculated_priority priority_enum,

            regular_amount NUMERIC(12, 2) CHECK (regular_amount >= 0),
            currency VARCHAR(3) DEFAULT 'UAH',
            is_trial BOOLEAN NOT NULL DEFAULT FALSE,
            trial_end_date DATE,
            discount_amount NUMERIC(12, 2) CHECK (discount_amount >= 0),
            discount_cycles_total INTEGER CHECK (discount_cycles_total > 0),
            discount_cycles_remaining INTEGER CHECK (discount_cycles_remaining >= 0),

            course_duration_days INTEGER CHECK (course_duration_days > 0),
            medication_start_date DATE,
            medication_end_date DATE,
            strict_schedule BOOLEAN NOT NULL DEFAULT FALSE
        );
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reminders_scheduler ON reminders (next_trigger_at, status)
        WHERE status IN ('ACTIVE', 'TRIAL') AND deleted_at IS NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reminders_user_type ON reminders (user_id, reminder_type)
        WHERE deleted_at IS NULL;
        """
    )

    # 8. Таблиця MEDICATION_INTAKE_LOGS
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS medication_intake_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            reminder_id UUID NOT NULL REFERENCES reminders(id) ON DELETE CASCADE,
            scheduled_at TIMESTAMPTZ NOT NULL,
            recorded_at TIMESTAMPTZ,
            status medication_log_status_enum NOT NULL DEFAULT 'MISSED',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ,
            version INTEGER NOT NULL DEFAULT 1
        );
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_medication_logs_reminder_scheduled
        ON medication_intake_logs (reminder_id, scheduled_at DESC)
        WHERE deleted_at IS NULL;
        """
    )

    # 9. Таблиця EXCHANGE_RATES (Append-Only)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            provider exchange_rate_provider_enum NOT NULL,
            base_currency VARCHAR(3) NOT NULL DEFAULT 'UAH',
            target_currency VARCHAR(3) NOT NULL,
            rate_buy NUMERIC(10, 4),
            rate_sell NUMERIC(10, 4) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_exchange_rates_provider_currency_created
        ON exchange_rates (provider, target_currency, created_at DESC);
        """
    )


def downgrade() -> None:
    """Видалення всіх таблиць, перелічень та функцій."""
    op.execute("DROP TABLE IF EXISTS exchange_rates CASCADE;")
    op.execute("DROP TABLE IF EXISTS medication_intake_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS reminders CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_settings CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_telegram_accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")

    op.execute("DROP TYPE IF EXISTS medication_log_status_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS end_of_month_policy_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS exchange_rate_provider_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS priority_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS reminder_status_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS schedule_logic_type_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS reminder_type_enum CASCADE;")
    op.execute("DROP TYPE IF EXISTS user_role_enum CASCADE;")

    op.execute("DROP FUNCTION IF EXISTS uuid_generate_v7();")
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto";')
