import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DbSettings(BaseModel):
    """Налаштування пулу підключень та доступу до PostgreSQL."""

    user: Annotated[str, Field(description="Користувач PostgreSQL")] = "reminder_user"
    password: Annotated[str, Field(description="Пароль до PostgreSQL")] = "reminder_secret_password"
    name: Annotated[str, Field(description="Назва бази даних PostgreSQL")] = "reminder_app"
    host: Annotated[str, Field(description="Хост сервера PostgreSQL")] = "127.0.0.1"
    port: Annotated[int, Field(description="Порт сервера PostgreSQL", ge=1, le=65535)] = 5434
    echo: Annotated[bool, Field(description="Виведення SQL-запитів у консоль")] = False

    pool_size: Annotated[int, Field(description="Базовий розмір пулу з'єднань", ge=1, le=100)] = 10
    max_overflow: Annotated[int, Field(description="Максимальне переповнення пулу з'єднань", ge=0, le=100)] = 10
    pool_timeout: Annotated[
        float,
        Field(description="Таймаут очікування вільного з'єднання з пулу у секундах", ge=1.0),
    ] = 30.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Повний URL підключення SQLAlchemy asyncpg."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisDBSettings(BaseModel):
    """Індекси логічних баз даних у Redis."""

    default: Annotated[int, Field(description="Індекс бази даних Redis за замовчуванням (кеш)", ge=0, le=15)] = 0
    task: Annotated[int, Field(description="Індекс бази даних Redis для фонових задач ARQ", ge=0, le=15)] = 1


class RedisSettings(BaseModel):
    """Налаштування підключення до Redis."""

    host: Annotated[str, Field(description="Хост сервера Redis")] = "127.0.0.1"
    port: Annotated[int, Field(description="Порт сервера Redis", ge=1, le=65535)] = 6379
    password: Annotated[str | None, Field(description="Пароль до Redis")] = "reminder_redis_password"
    databases: Annotated[
        RedisDBSettings,
        Field(description="Індекси логічних баз даних Redis"),
    ] = RedisDBSettings()
    notification_queue_key: Annotated[
        str,
        Field(description="Ключ списку Redis для черги повідомлень Telegram"),
    ] = "queue:notifications:telegram"

    def get_url(self, db: int | None = None) -> str:
        """Генерує URL підключення до Redis для вказаного індексу бази даних."""
        target_db = db if db is not None else self.databases.default
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{target_db}"
        return f"redis://{self.host}:{self.port}/{target_db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Базовий URL підключення до Redis за замовчуванням."""
        return self.get_url(self.databases.default)


class AuthSettings(BaseModel):
    """Налаштування безпеки, паролів та JWT-токенів."""

    access_secret_key: Annotated[
        str,
        Field(description="Секретний ключ підпису access-токенів JWT", min_length=32),
    ] = "local-dev-secret-key-min-32-chars-for-reminder-app"
    internal_token: Annotated[
        str,
        Field(description="Секретний токен для внутрішньої автентифікації бота", min_length=16),
    ] = "local-dev-internal-bot-token-min-32-chars"
    algorithm: Annotated[str, Field(description="Алгоритм шифрування JWT")] = "HS256"
    access_token_expire_minutes: Annotated[
        int,
        Field(description="Час життя access-токена у хвилинах", ge=1),
    ] = 60
    bcrypt_rounds: Annotated[
        int,
        Field(description="Кількість раундів хешування паролів bcrypt", ge=4, le=31),
    ] = 12


class ApiSettings(BaseModel):
    """Конфігурація HTTP API та політики CORS."""

    v1_prefix: Annotated[str, Field(description="Префікс маршрутів API v1")] = "/api/v1"
    cors_origins: Annotated[list[str], Field(description="Список дозволених CORS джерел")] = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8000",
    ]


class RateLimitSettings(BaseModel):
    """Конфігурація обмеження частоти HTTP-запитів (Rate Limiting)."""

    enabled: Annotated[bool, Field(description="Глобальний прапорець активності рейт-лімітера")] = True
    default_limit: Annotated[str, Field(description="Глобальний ліміт частоти запитів за замовчуванням")] = "200/minute"
    auth_login_limit: Annotated[str, Field(description="Ліміт спроб входу за логіном")] = "5/minute"
    password_change_limit: Annotated[str, Field(description="Ліміт спроб зміни пароля")] = "5/minute"
    password_admin_limit: Annotated[str, Field(description="Ліміт адмінського встановлення пароля")] = "10/minute"
    user_create_limit: Annotated[str, Field(description="Ліміт створення користувачів")] = "20/minute"
    reminder_write_limit: Annotated[str, Field(description="Ліміт створення та оновлення нагадувань")] = "30/minute"
    bank_sync_limit: Annotated[str, Field(description="Ліміт ручної синхронізації курсів валют з банками")] = "5/minute"


class ArqSettings(BaseModel):
    """Конфігурація фонового планувальника задач ARQ."""

    max_jobs: Annotated[
        int,
        Field(description="Максимальна кількість паралельних задач у воркері ARQ", ge=1, le=100),
    ] = 10
    job_timeout: Annotated[int, Field(description="Таймаут виконання задачі у секундах", ge=1)] = 300
    max_tries: Annotated[int, Field(description="Максимальна кількість повторних спроб виконання задачі", ge=1)] = 3
    keep_result: Annotated[
        int,
        Field(description="Тривалість збереження результату задачі у Redis у секундах", ge=0),
    ] = 3600
    health_check_interval: Annotated[
        int,
        Field(description="Інтервал перевірки працездатності воркера у секундах", ge=1),
    ] = 30
    queue_name: Annotated[str, Field(description="Назва черги ARQ у Redis")] = "arq:queue"


class FinanceSettings(BaseModel):
    """Налаштування інтеграції з банківськими API курсів валют."""

    nbu_api_url: Annotated[
        str,
        Field(description="URL публічного API НБУ для отримання курсів валют"),
    ] = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
    monobank_api_url: Annotated[
        str,
        Field(description="URL публічного API Monobank для курсів валют"),
    ] = "https://api.monobank.ua/bank/currency"
    privatbank_api_url: Annotated[
        str,
        Field(description="URL публічного API ПриватБанку для курсів валют"),
    ] = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"
    http_timeout_seconds: Annotated[
        float,
        Field(description="Таймаут HTTP-запитів до банківських API у секундах", ge=1.0),
    ] = 10.0
    stale_rate_hours: Annotated[
        int,
        Field(description="Кількість годин, після якої курс вважається застарілим", ge=1),
    ] = 48


class BotSettings(BaseModel):
    """Конфігурація сервісу Telegram-бота."""

    token: Annotated[
        str,
        Field(description="Токен авторизації Telegram-бота від BotFather"),
    ] = "0000000000:AAH_placeholder_telegram_bot_token"
    backend_api_url: Annotated[
        str,
        Field(description="Базовий URL внутрішнього API бекенду для звернень бота"),
    ] = "http://backend:8000/api/v1"


class LogSettings(BaseModel):
    """Конфігурація логування Loguru."""

    dir: Annotated[Path, Field(description="Директорія зберігання логів")] = Path("logs")
    app_file: Annotated[str, Field(description="Назва файлу логів веб-додатку")] = "app/app.log"
    worker_file: Annotated[str, Field(description="Назва файлу логів фонового воркера")] = "worker/worker.log"
    bot_file: Annotated[str, Field(description="Назва файлу логів бота")] = "bot/bot.log"
    level: Annotated[str, Field(description="Рівень деталізації логування")] = "INFO"
    rotation: Annotated[str, Field(description="Правило ротації файлів логів")] = "50 MB"
    retention: Annotated[str, Field(description="Термін зберігання архівованих файлів логів")] = "7 days"

    @property
    def app_log_path(self) -> Path:
        """Повний шлях до файлу логів веб-додатку."""
        return self.dir / self.app_file

    @property
    def worker_log_path(self) -> Path:
        """Повний шлях до файлу логів фонового воркера."""
        return self.dir / self.worker_file

    @property
    def bot_log_path(self) -> Path:
        """Повний шлях до файлу логів Telegram-бота."""
        return self.dir / self.bot_file


class SeedSettings(BaseModel):
    """Конфігурація початкових системних користувачів."""

    superadmin_username: Annotated[
        str,
        Field(description="Початковий логін суперадміністратора"),
    ] = "super_admin"
    superadmin_password: Annotated[
        str,
        Field(description="Початковий пароль суперадміністратора", min_length=8),
    ] = "super_admin_password"


class Settings(BaseSettings):
    """Головний агрегат конфігурації проєкту Reminder App."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
        extra="ignore",
    )

    environment: Annotated[
        str,
        Field(description="Середовище запуску додатку (local, test, staging, production)"),
    ] = "local"

    db: Annotated[
        DbSettings,
        Field(description="Конфігурація бази даних PostgreSQL"),
    ] = DbSettings()
    redis: Annotated[
        RedisSettings,
        Field(description="Конфігурація Redis"),
    ] = RedisSettings()
    auth: Annotated[
        AuthSettings,
        Field(description="Конфігурація безпеки та автентифікації"),
    ] = AuthSettings()
    api: Annotated[
        ApiSettings,
        Field(description="Конфігурація HTTP API"),
    ] = ApiSettings()
    rate_limit: Annotated[
        RateLimitSettings,
        Field(description="Конфігурація обмеження частоти HTTP-запитів"),
    ] = RateLimitSettings()
    arq: Annotated[
        ArqSettings,
        Field(description="Конфігурація фонового планувальника ARQ"),
    ] = ArqSettings()
    finance: Annotated[
        FinanceSettings,
        Field(description="Конфігурація фінансового модуля та банківських API"),
    ] = FinanceSettings()
    bot: Annotated[
        BotSettings,
        Field(description="Конфігурація сервісу Telegram-бота"),
    ] = BotSettings()
    log: Annotated[
        LogSettings,
        Field(description="Конфігурація структурованого логування"),
    ] = LogSettings()
    seed: Annotated[
        SeedSettings,
        Field(description="Конфігурація початкових системних облікових записів"),
    ] = SeedSettings()

    @property
    def is_testing(self) -> bool:
        """Визначає, чи додаток виконується в тестовому середовищі."""
        return self.environment == "test" or "pytest" in sys.modules

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Перевірка криптографічної стійкості налаштувань для бойового середовища."""
        if self.environment in ("production", "prod") and self.auth.bcrypt_rounds < 12:
            raise ValueError(
                f"Критична помилка безпеки: у середовищі '{self.environment}' "
                f"мінімальна кількість раундів bcrypt — 12 (передано: {self.auth.bcrypt_rounds})!"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Отримання кешованого синглтона налаштувань додатку."""
    return Settings()


settings = get_settings()
