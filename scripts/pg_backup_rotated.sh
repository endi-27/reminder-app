#!/bin/sh
set -e

# Імпорт змінних оточення (необхідно для коректної роботи в crond)
[ -f /etc/environment ] && . /etc/environment

# --- КОНФІГУРАЦІЯ (збирається зі змінних оточення) ---
HOSTNAME="${APP_CONFIG__DB__HOST:-postgres}"
USERNAME="${APP_CONFIG__DB__USER:-reminder_user}"
DATABASE="${APP_CONFIG__DB__NAME:-reminder_app}"
PGPASSWORD="${APP_CONFIG__DB__PASSWORD:-reminder_secret_password}"
export PGPASSWORD

BACKUP_DIR="${BACKUPS_DIR:-/backups}"
DAYS_TO_KEEP="${BACKUP_RETENTION_DAYS:-7}"

DATE_PREFIX=$(date +%Y-%m-%d_%H-%M-%S)
FINAL_BACKUP_DIR="${BACKUP_DIR}/${DATE_PREFIX}-daily"

echo "[$(date)] *** Початок створення бекапу для БД: ${DATABASE}"

# Створення папки бекапу
mkdir -p "${FINAL_BACKUP_DIR}"

# 1. Створення дампа системних ролей/глобальних об'єктів (Globals)
GLOBALS_FILE="${FINAL_BACKUP_DIR}/globals.sql.gz"
echo "[$(date)] Дамп глобальних об'єктів..."
if pg_dumpall -h "${HOSTNAME}" -U "${USERNAME}" -g | gzip > "${GLOBALS_FILE}.in_progress"; then
    mv "${GLOBALS_FILE}.in_progress" "${GLOBALS_FILE}"
else
    echo "[!!ERROR!!] Не вдалося створити бекап globals" >&2
    rm -f "${GLOBALS_FILE}.in_progress"
fi

# 2. Створення стисненого дампа основної бази даних
DB_FILE="${FINAL_BACKUP_DIR}/${DATABASE}.sql.gz"
echo "[$(date)] Дамп бази даних ${DATABASE}..."
if pg_dump -h "${HOSTNAME}" -U "${USERNAME}" -Fp "${DATABASE}" | gzip > "${DB_FILE}.in_progress"; then
    mv "${DB_FILE}.in_progress" "${DB_FILE}"
    FILE_SIZE=$(du -h "${DB_FILE}" | cut -f1)
    echo "[$(date)] Бекап успішно створено: ${DB_FILE} (Розмір: ${FILE_SIZE})"
else
    echo "[!!ERROR!!] Помилка під час створення дампа бази ${DATABASE}" >&2
    rm -f "${DB_FILE}.in_progress"
    exit 1
fi

# 3. Ротація (Видалення бекапів, старіших за задану кількість днів)
echo "[$(date)] Очищення бекапів, старіших за ${DAYS_TO_KEEP} днів..."
find "${BACKUP_DIR}" -maxdepth 1 -type d -name "*-daily" -mtime +"${DAYS_TO_KEEP}" -exec rm -rf '{}' '+'

echo "[$(date)] *** Процес бекапування завершено."
