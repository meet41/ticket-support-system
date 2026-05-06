import logging

import redis.asyncio as aioredis

from app.config.settings import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


async def connect_to_redis() -> None:
    global _redis
    _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await _redis.ping()
    logger.info("Connected to Redis at %s", settings.REDIS_URL)


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        logger.info("Redis connection closed.")


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised. Call connect_to_redis() during startup.")
    return _redis