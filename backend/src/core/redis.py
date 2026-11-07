from __future__ import annotations

from typing import TYPE_CHECKING, Any

from redis.asyncio import ConnectionPool, Redis

from src.core.config import settings

if TYPE_CHECKING:
    RedisClient = Redis[Any]
    RedisPool = ConnectionPool[Any]
else:
    RedisClient = Redis
    RedisPool = ConnectionPool

_redis_pools: dict[int, RedisPool] = {}


def get_redis_pool(db: int | None = None) -> RedisPool:
    """Отримання або створення пулу підключень до Redis для вказаної БД."""
    global _redis_pools
    target_db = db if db is not None else settings.redis.databases.default
    if target_db not in _redis_pools:
        _redis_pools[target_db] = ConnectionPool.from_url(
            settings.redis.get_url(target_db),
            max_connections=20,
            decode_responses=True,
        )
    return _redis_pools[target_db]


def get_redis_client(db: int | None = None) -> RedisClient:
    """Отримання асинхронного клієнта Redis для вказаної БД (за замовчуванням default)."""
    return Redis(connection_pool=get_redis_pool(db))


async def close_redis() -> None:
    """Закриття всіх активних пулів підключень до Redis."""
    global _redis_pools
    for pool in _redis_pools.values():
        await pool.disconnect()
    _redis_pools.clear()
