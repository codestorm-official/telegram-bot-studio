"""PostgreSQL access layer backed by an asyncpg connection pool."""

import json
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

# Dynamic commands managed through the admin panel. `keyboard` holds an optional
# reply-keyboard layout as JSON (list of rows of button labels).
CREATE_COMMANDS_TABLE = """
CREATE TABLE IF NOT EXISTS commands (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT NOT NULL DEFAULT '',
    reply_type   TEXT NOT NULL DEFAULT 'text',
    reply_text   TEXT NOT NULL DEFAULT '',
    media_url    TEXT NOT NULL DEFAULT '',
    keyboard     JSONB,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    show_in_menu BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

CREATE_MENU_BUTTONS_TABLE = """
CREATE TABLE IF NOT EXISTS menu_buttons (
    id           SERIAL PRIMARY KEY,
    label        TEXT NOT NULL UNIQUE,
    command_name TEXT NOT NULL,
    row_index    INTEGER NOT NULL DEFAULT 0 CHECK (row_index >= 0),
    sort_order   INTEGER NOT NULL DEFAULT 0,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

COMMAND_COLUMNS = (
    "id, name, description, reply_type, reply_text, media_url, "
    "keyboard, enabled, show_in_menu, created_at, updated_at"
)


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
        await conn.execute(CREATE_COMMANDS_TABLE)
        await conn.execute(CREATE_MENU_BUTTONS_TABLE)
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


# --- Dynamic command management (admin panel) --------------------------------


def _command_to_dict(row: asyncpg.Record) -> dict:
    """Normalise a command row into a plain dict, decoding the keyboard JSON."""
    data = dict(row)
    keyboard = data.get("keyboard")
    if isinstance(keyboard, str):
        try:
            data["keyboard"] = json.loads(keyboard)
        except (ValueError, TypeError):
            data["keyboard"] = None
    return data


async def list_commands(pool: asyncpg.Pool, *, enabled_only: bool = False) -> list[dict]:
    """Return all commands ordered by name (optionally only enabled ones)."""
    query = f"SELECT {COMMAND_COLUMNS} FROM commands"
    if enabled_only:
        query += " WHERE enabled = TRUE"
    query += " ORDER BY name;"
    rows = await pool.fetch(query)
    return [_command_to_dict(row) for row in rows]


async def get_command(pool: asyncpg.Pool, command_id: int) -> dict | None:
    row = await pool.fetchrow(
        f"SELECT {COMMAND_COLUMNS} FROM commands WHERE id = $1;", command_id
    )
    return _command_to_dict(row) if row is not None else None


async def create_command(
    pool: asyncpg.Pool,
    *,
    name: str,
    description: str,
    reply_type: str,
    reply_text: str,
    media_url: str,
    keyboard: list | None,
    enabled: bool,
    show_in_menu: bool,
) -> dict:
    row = await pool.fetchrow(
        f"""
        INSERT INTO commands
            (name, description, reply_type, reply_text, media_url,
             keyboard, enabled, show_in_menu)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING {COMMAND_COLUMNS};
        """,
        name,
        description,
        reply_type,
        reply_text,
        media_url,
        json.dumps(keyboard) if keyboard else None,
        enabled,
        show_in_menu,
    )
    return _command_to_dict(row)


async def update_command(
    pool: asyncpg.Pool,
    command_id: int,
    *,
    name: str,
    description: str,
    reply_type: str,
    reply_text: str,
    media_url: str,
    keyboard: list | None,
    enabled: bool,
    show_in_menu: bool,
) -> dict | None:
    row = await pool.fetchrow(
        f"""
        UPDATE commands SET
            name = $2, description = $3, reply_type = $4, reply_text = $5,
            media_url = $6, keyboard = $7, enabled = $8, show_in_menu = $9,
            updated_at = now()
        WHERE id = $1
        RETURNING {COMMAND_COLUMNS};
        """,
        command_id,
        name,
        description,
        reply_type,
        reply_text,
        media_url,
        json.dumps(keyboard) if keyboard else None,
        enabled,
        show_in_menu,
    )
    return _command_to_dict(row) if row is not None else None


async def delete_command(pool: asyncpg.Pool, command_id: int) -> bool:
    result = await pool.execute("DELETE FROM commands WHERE id = $1;", command_id)
    # asyncpg returns a status string like "DELETE 1".
    return result.endswith("1")


async def update_command_keyboard(
    pool: asyncpg.Pool, command_id: int, keyboard: list | None
) -> dict | None:
    """Replace only a command's response-button layout."""
    row = await pool.fetchrow(
        f"""
        UPDATE commands
        SET keyboard = $2, updated_at = now()
        WHERE id = $1
        RETURNING {COMMAND_COLUMNS};
        """,
        command_id,
        json.dumps(keyboard) if keyboard else None,
    )
    return _command_to_dict(row) if row is not None else None


# --- Main reply-keyboard buttons --------------------------------------------


async def list_menu_buttons(
    pool: asyncpg.Pool, *, enabled_only: bool = False
) -> list[dict]:
    query = "SELECT * FROM menu_buttons"
    if enabled_only:
        query += " WHERE enabled = TRUE"
    query += " ORDER BY row_index, sort_order, id;"
    return [dict(row) for row in await pool.fetch(query)]


async def create_menu_button(
    pool: asyncpg.Pool,
    *,
    label: str,
    command_name: str,
    row_index: int,
    sort_order: int,
    enabled: bool,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO menu_buttons
            (label, command_name, row_index, sort_order, enabled)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *;
        """,
        label,
        command_name,
        row_index,
        sort_order,
        enabled,
    )
    return dict(row)


async def delete_menu_button(pool: asyncpg.Pool, button_id: int) -> bool:
    result = await pool.execute("DELETE FROM menu_buttons WHERE id = $1;", button_id)
    return result.endswith("1")
