"""In-process registry of dynamic commands managed through the admin panel.

Postgres is the source of truth; this module keeps a process-local copy that the
bot reads on every update and that the panel refreshes after each change. Because
the bot and the panel run in the same process, a direct ``reload()`` call is all
the invalidation we need (no cross-process cache required).
"""

import logging

from telegram import Message, ReplyKeyboardMarkup

from bot import db


logger = logging.getLogger(__name__)

# Reply types supported by the panel / dispatcher.
REPLY_TYPES = ("text", "photo", "document")

# Built-in commands handled in code; dynamic commands must not shadow them.
RESERVED_NAMES = frozenset({"start", "help", "about", "ping"})

# name -> command dict (enabled commands only).
_REGISTRY: dict[str, dict] = {}


async def reload(pool) -> None:
    """Reload the enabled commands from Postgres into the in-process registry."""
    global _REGISTRY
    if pool is None:
        _REGISTRY = {}
        return
    commands = await db.list_commands(pool, enabled_only=True)
    _REGISTRY = {cmd["name"]: cmd for cmd in commands}
    logger.info("Loaded %d dynamic command(s).", len(_REGISTRY))


def lookup(name: str) -> dict | None:
    """Return the command registered under ``name`` (without slash), or None."""
    return _REGISTRY.get(name.lower())


def menu_commands() -> list[tuple[str, str]]:
    """Return (name, description) pairs for commands that opt into the menu."""
    return [
        (cmd["name"], cmd["description"] or cmd["name"])
        for cmd in sorted(_REGISTRY.values(), key=lambda c: c["name"])
        if cmd.get("show_in_menu")
    ]


def _build_keyboard(keyboard: list | None) -> ReplyKeyboardMarkup | None:
    """Turn a stored layout (list of rows of labels) into a reply keyboard."""
    if not keyboard:
        return None
    rows = [[str(label) for label in row] for row in keyboard if row]
    if not rows:
        return None
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


async def send(message: Message, command: dict) -> None:
    """Send a command's configured reply (text / photo / document + keyboard)."""
    markup = _build_keyboard(command.get("keyboard"))
    reply_type = command.get("reply_type", "text")
    text = command.get("reply_text") or ""
    media_url = command.get("media_url") or ""

    if reply_type == "photo" and media_url:
        await message.reply_photo(photo=media_url, caption=text or None, reply_markup=markup)
    elif reply_type == "document" and media_url:
        await message.reply_document(
            document=media_url, caption=text or None, reply_markup=markup
        )
    else:
        # Fall back to text when no media is configured.
        await message.reply_text(text or " ", reply_markup=markup)
