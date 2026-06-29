"""Redis access layer using the async redis-py client."""

import logging

import redis.asyncio as redis


logger = logging.getLogger(__name__)

# Keep network hiccups from blocking the update loop.
SOCKET_TIMEOUT = 5.0

# Keys / TTLs for the demo features.
MESSAGE_COUNT_KEY = "bot:messages:{telegram_id}"
PING_CACHE_KEY = "bot:ping"
PING_CACHE_TTL = 10  # seconds


async def create_client(url: str) -> redis.Redis:
    """Open the Redis client and verify connectivity with PING. Raises on failure."""
    client = redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT,
        socket_connect_timeout=SOCKET_TIMEOUT,
    )
    await client.ping()
    logger.info("Redis client ready.")
    return client


async def increment_message_count(client: redis.Redis, telegram_id: int) -> int:
    """Increment and return the per-user message counter."""
    return int(await client.incr(MESSAGE_COUNT_KEY.format(telegram_id=telegram_id)))


async def get_message_count(client: redis.Redis, telegram_id: int) -> int:
    value = await client.get(MESSAGE_COUNT_KEY.format(telegram_id=telegram_id))
    return int(value) if value is not None else 0


async def get_or_set_ping(client: redis.Redis) -> bool:
    """Return True if a cached ping is still warm, else set it and return False."""
    cached = await client.get(PING_CACHE_KEY)
    if cached is not None:
        return True
    await client.set(PING_CACHE_KEY, "1", ex=PING_CACHE_TTL)
    return False


async def close_client(client: redis.Redis) -> None:
    await client.aclose()
    logger.info("Redis client closed.")
