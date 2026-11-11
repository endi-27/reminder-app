from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings

# Ініціалізація SlowAPI Limiter з використанням Redis для розподіленого rate limiting.
# Автоматично вимикається у тестовому середовищі (settings.is_testing) або за прапорцем settings.rate_limit.enabled.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit.default_limit],
    storage_uri=settings.redis.url,
    enabled=settings.rate_limit.enabled and not settings.is_testing,
)
