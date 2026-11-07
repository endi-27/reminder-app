from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient

from src.core.config import settings


@pytest.mark.asyncio
async def test_healthcheck_endpoint(api_client: AsyncClient) -> None:
    """
    Перевірка ендпоінту працездатності GET /api/v1/health:
    перевіряє статус сервісу, підключення до PostgreSQL та Redis.
    """
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_telegram_sync_and_user_settings_occ_flow(api_client: AsyncClient) -> None:
    """
    Наскрізний сценарій реєстрації через Telegram, автентифікації бота
    та оновлення налаштувань із контролем оптимістичного блокування (OCC).
    """
    bot_token_headers = {"X-Internal-Token": settings.auth.internal_token}
    telegram_id = 99887766

    # 1. Синхронізація (реєстрація) сесії користувача ботом
    sync_payload = {
        "telegram_id": telegram_id,
        "telegram_chat_id": telegram_id,
        "tg_username": "e2e_tg_user",
        "tg_full_name": "E2E Test User",
        "timezone": "Europe/Kyiv",
    }
    sync_resp = await api_client.post(
        "/api/v1/users/telegram/sync",
        headers=bot_token_headers,
        json=sync_payload,
    )
    assert sync_resp.status_code == 200
    user_data = sync_resp.json()
    assert user_data["username"] == "e2e_tg_user"

    # Заголовки для подальших запитів бота від імені цього користувача
    user_headers = {
        "X-Internal-Token": settings.auth.internal_token,
        "X-Telegram-Id": str(telegram_id),
    }

    # 2. Отримання власного профілю
    profile_resp = await api_client.get("/api/v1/users/me", headers=user_headers)
    assert profile_resp.status_code == 200
    assert profile_resp.json()["id"] == user_data["id"]

    # 3. Отримання налаштувань
    settings_resp = await api_client.get("/api/v1/users/me/settings", headers=user_headers)
    assert settings_resp.status_code == 200
    current_settings = settings_resp.json()
    assert current_settings["version"] == 1
    assert current_settings["timezone"] == "Europe/Kyiv"

    # 4. Успішне оновлення налаштувань (version = 1 -> version = 2)
    update_resp = await api_client.patch(
        "/api/v1/users/me/settings",
        headers=user_headers,
        json={
            "version": 1,
            "preferred_bank": "MONOBANK",
            "timezone": "Europe/Kyiv",
        },
    )
    assert update_resp.status_code == 200
    updated_settings = update_resp.json()
    assert updated_settings["version"] == 2
    assert updated_settings["preferred_bank"] == "MONOBANK"

    # 5. Спроба повторного оновлення зі застарілою версією 1 -> 409 Conflict
    conflict_resp = await api_client.patch(
        "/api/v1/users/me/settings",
        headers=user_headers,
        json={
            "version": 1,
            "preferred_bank": "PRIVATBANK",
        },
    )
    assert conflict_resp.status_code == 409
    error_body = conflict_resp.json()
    assert error_body["error"]["code"] == "OPTIMISTIC_LOCK_CONFLICT"


@pytest.mark.asyncio
async def test_reminders_crud_lifecycle_and_compatibility_validation(api_client: AsyncClient) -> None:
    """
    Повний E2E сценарій життєвого циклу нагадувань через HTTP API:
    - Валідація матриці сумісності типів нагадувань та логік планування (422).
    - Створення всіх основних типів (ANNIVERSARY, DEADLINE_TASK, SUBSCRIPTION, MEDICATION).
    - Повне оновлення (PUT) з перевіркою версії OCC.
    - Виконання дій (POST /actions) для підписки та прийому ліків.
    - Перевірка журналу комплаєнсу та статистики прийому медикаментів.
    - Видалення (DELETE / Soft Delete).
    """
    telegram_id = 77665544
    bot_token_headers = {"X-Internal-Token": settings.auth.internal_token}

    # Реєструємо тестового користувача
    await api_client.post(
        "/api/v1/users/telegram/sync",
        headers=bot_token_headers,
        json={
            "telegram_id": telegram_id,
            "telegram_chat_id": telegram_id,
            "tg_username": "reminders_e2e_user",
        },
    )

    user_headers = {
        "X-Internal-Token": settings.auth.internal_token,
        "X-Telegram-Id": str(telegram_id),
    }

    now = datetime.now(UTC)

    # 1. Валідація несумісної пари (ANNIVERSARY + DAILY_AT_TIMES -> 400/422 INCOMPATIBLE_SCHEDULE_LOGIC)
    incompatible_resp = await api_client.post(
        "/api/v1/reminders",
        headers=user_headers,
        json={
            "reminder_type": "ANNIVERSARY",
            "schedule_logic": "DAILY_AT_TIMES",
            "title": "Несумісне нагадування",
            "schedule_config": {"times": ["10:00:00"]},
        },
    )
    assert incompatible_resp.status_code in (400, 422)
    assert "INCOMPATIBLE_SCHEDULE_LOGIC" in incompatible_resp.text

    # 2. Створення Anniversary (ANNIVERSARY + DATE_WITH_MONTH_INTERVAL)
    anniv_resp = await api_client.post(
        "/api/v1/reminders",
        headers=user_headers,
        json={
            "reminder_type": "ANNIVERSARY",
            "schedule_logic": "DATE_WITH_MONTH_INTERVAL",
            "title": "Річниця весілля",
            "schedule_config": {
                "day": 10,
                "month": 8,
                "interval_months": 12,
                "target_time": "09:00:00",
                "birth_year": 2018,
            },
            "lead_times": ["7d", "1d"],
        },
    )
    assert anniv_resp.status_code == 201
    anniv_data = anniv_resp.json()
    anniv_id = anniv_data["id"]
    assert anniv_data["title"] == "Річниця весілля"
    assert anniv_data["version"] == 1

    # 3. Створення Deadline Task (DEADLINE_TASK + EXACT_DATETIME_DEADLINE)
    deadline_dt = now + timedelta(days=2)
    deadline_resp = await api_client.post(
        "/api/v1/reminders",
        headers=user_headers,
        json={
            "reminder_type": "DEADLINE_TASK",
            "schedule_logic": "EXACT_DATETIME_DEADLINE",
            "title": "Оплатити комуналку",
            "schedule_config": {"due_datetime": deadline_dt.isoformat()},
            "due_datetime": deadline_dt.isoformat(),
            "base_priority": "HIGH",
            "lead_times": ["1d", "2h"],
        },
    )
    assert deadline_resp.status_code == 201
    deadline_data = deadline_resp.json()
    deadline_id = deadline_data["id"]
    assert deadline_data["base_priority"] == "HIGH"

    # 4. Створення Subscription (SUBSCRIPTION з тріалом та знижкою)
    sub_resp = await api_client.post(
        "/api/v1/reminders",
        headers=user_headers,
        json={
            "reminder_type": "SUBSCRIPTION",
            "schedule_logic": "DATE_WITH_MONTH_INTERVAL",
            "title": "Онлайн кінотеатр",
            "schedule_config": {
                "day": 1,
                "interval_months": 1,
                "target_time": "12:00:00",
            },
            "regular_amount": "14.99",
            "currency": "USD",
            "is_trial": True,
            "trial_end_date": (date.today() + timedelta(days=7)).isoformat(),
            "discount_amount": "7.99",
            "discount_cycles_total": 2,
            "discount_cycles_remaining": 2,
        },
    )
    assert sub_resp.status_code == 201
    sub_data = sub_resp.json()
    sub_id = sub_data["id"]
    assert sub_data["is_trial"] is True
    assert sub_data["discount_cycles_remaining"] == 2

    # 5. Створення Medication (MEDICATION зі strict_schedule=True)
    med_resp = await api_client.post(
        "/api/v1/reminders",
        headers=user_headers,
        json={
            "reminder_type": "MEDICATION",
            "schedule_logic": "DAILY_AT_TIMES",
            "title": "Антибіотик Амоксиклав",
            "schedule_config": {"times": ["08:00:00", "20:00:00"]},
            "medication_start_date": date.today().isoformat(),
            "course_duration_days": 7,
            "strict_schedule": True,
        },
    )
    assert med_resp.status_code == 201
    med_data = med_resp.json()
    med_id = med_data["id"]
    assert med_data["strict_schedule"] is True

    # 6. Повне оновлення (PUT) нагадування дедлайну
    put_resp = await api_client.put(
        f"/api/v1/reminders/{deadline_id}",
        headers=user_headers,
        json={
            "version": 1,
            "schedule_logic": "EXACT_DATETIME_DEADLINE",
            "title": "Оплатити комуналку (терміново)",
            "description": "Перевірити показники лічильника",
            "schedule_config": {"due_datetime": deadline_dt.isoformat()},
            "due_datetime": deadline_dt.isoformat(),
            "base_priority": "CRITICAL",
            "lead_times": ["12h", "1h"],
            "status": "ACTIVE",
        },
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["version"] == 2
    assert put_data["title"] == "Оплатити комуналку (терміново)"
    assert put_data["base_priority"] == "CRITICAL"

    # Спроба повторного PUT зі застарілою версією 1 -> 409 Conflict
    put_conflict_resp = await api_client.put(
        f"/api/v1/reminders/{deadline_id}",
        headers=user_headers,
        json={
            "version": 1,
            "schedule_logic": "EXACT_DATETIME_DEADLINE",
            "title": "Конфліктний заголовок",
            "schedule_config": {"due_datetime": deadline_dt.isoformat()},
            "status": "ACTIVE",
        },
    )
    assert put_conflict_resp.status_code == 409

    # 7. Дія над підпискою: RECORD_PAYMENT
    action_pay_resp = await api_client.post(
        f"/api/v1/reminders/{sub_id}/actions",
        headers=user_headers,
        json={"action": "RECORD_PAYMENT"},
    )
    assert action_pay_resp.status_code == 200
    paid_sub = action_pay_resp.json()
    # Тріал скинувся у платний режим, списався один цикл знижки (залишився 1)
    assert paid_sub["is_trial"] is False
    assert paid_sub["discount_cycles_remaining"] == 1

    # 8. Дія над ліками: RECORD_MEDICATION_INTAKE (TAKEN)
    action_med_resp = await api_client.post(
        f"/api/v1/reminders/{med_id}/actions",
        headers=user_headers,
        json={
            "action": "RECORD_MEDICATION_INTAKE",
            "medication_status": "TAKEN",
        },
    )
    assert action_med_resp.status_code == 200

    # 9. Отримання журналу та статистики прийому ліків
    logs_resp = await api_client.get(
        f"/api/v1/reminders/{med_id}/medication-logs",
        headers=user_headers,
    )
    assert logs_resp.status_code == 200
    stats_data = logs_resp.json()
    assert stats_data["total_logs"] >= 1
    assert stats_data["taken_count"] >= 1
    assert stats_data["adherence_rate_percent"] == 100.0
    assert len(stats_data["logs"]) >= 1

    # 10. Видалення нагадування (DELETE)
    del_resp = await api_client.delete(f"/api/v1/reminders/{anniv_id}", headers=user_headers)
    assert del_resp.status_code == 204

    # Перевірка, що видалене нагадування повертає 404
    get_del_resp = await api_client.get(f"/api/v1/reminders/{anniv_id}", headers=user_headers)
    assert get_del_resp.status_code == 404
