"""PostgreSQL access layer backed by an asyncpg connection pool."""

import logging

import asyncpg


logger = logging.getLogger(__name__)

# Connection/command guards so a stalled database never hangs the bot.
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 10
COMMAND_TIMEOUT = 10.0

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

UPSERT_USER = """
INSERT INTO users (telegram_id, username, first_name)
VALUES ($1, $2, $3)
ON CONFLICT (telegram_id) DO UPDATE
    SET username   = EXCLUDED.username,
        first_name = EXCLUDED.first_name,
        last_seen  = now()
RETURNING (xmax = 0) AS is_new;
"""


async def create_pool(dsn: str) -> asyncpg.Pool:
    """Open the connection pool and ensure the schema exists. Raises on failure."""
    pool = await asyncpg.create_pool(
        dsn,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        command_timeout=COMMAND_TIMEOUT,
    )
    async with pool.acquire() as conn:
        await conn.execute(CREATE_USERS_TABLE)
    logger.info("PostgreSQL pool ready (schema initialized).")
    return pool


async def upsert_user(
    pool: asyncpg.Pool,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
) -> bool:
    """Insert or refresh a user. Returns True if this is a brand-new user."""
    is_new = await pool.fetchval(UPSERT_USER, telegram_id, username, first_name)
    return bool(is_new)


async def count_users(pool: asyncpg.Pool) -> int:
    """Return the total number of known users."""
    return int(await pool.fetchval("SELECT count(*) FROM users;"))


async def close_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
    logger.info("PostgreSQL pool closed.")
