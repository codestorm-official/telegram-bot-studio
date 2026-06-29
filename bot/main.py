"""Entrypoint for the Telegram bot (and the optional admin panel)."""

import asyncio
import logging

import uvicorn
from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from bot import cache, commands, db
from bot.config import Settings
from bot.handlers import (
    DB_KEY,
    REDIS_KEY,
    error_handler,
    register_handlers,
    set_bot_commands,
)
from bot.panel.app import create_app


logger = logging.getLogger(__name__)


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
        level=level,
    )


async def _connect_optional(name, url, connect):
    """Connect to an optional backend, returning None when unavailable.

    Missing/empty URL -> skipped with a warning. Connection failure -> logged as
    an error but the bot keeps running without that backend.
    """
    if not url:
        logger.warning("%s URL not set - running without it.", name)
        return None
    try:
        return await connect(url)
    except Exception:
        logger.exception("%s unavailable - running without it.", name)
        return None


def build_application(settings: Settings) -> Application:
    async def on_startup(application: Application) -> None:
        # Optional backends: the bot runs even when DATABASE_URL / REDIS_URL are
        # missing or unreachable, degrading gracefully instead of refusing to start.
        application.bot_data[DB_KEY] = await _connect_optional(
            "PostgreSQL", settings.database_url, db.create_pool
        )
        application.bot_data[REDIS_KEY] = await _connect_optional(
            "Redis", settings.redis_url, cache.create_client
        )
        # Load panel-managed commands before publishing the Telegram menu.
        await commands.reload(application.bot_data[DB_KEY])
        try:
            await set_bot_commands(application)
        except Exception:
            # A rejected menu must not stop the bot from starting.
            logger.exception("Failed to publish command menu on startup.")

    async def on_shutdown(application: Application) -> None:
        pool = application.bot_data.get(DB_KEY)
        if pool is not None:
            await db.close_pool(pool)

        client = application.bot_data.get(REDIS_KEY)
        if client is not None:
            await cache.close_client(client)

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    register_handlers(application)
    application.add_error_handler(error_handler)
    return application


async def _run_with_panel(application: Application, settings: Settings) -> None:
    """Run Telegram polling and the admin panel together in one event loop."""
    await application.initialize()  # triggers on_startup (connect + load commands)
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot polling started; admin panel listening on port %d.", settings.port)

    web = create_app(application, settings)
    config = uvicorn.Config(
        web,
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()  # blocks until SIGTERM/SIGINT
    finally:
        if application.updater is not None and application.updater.running:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()  # triggers on_shutdown (close pool/redis)


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    application = build_application(settings)

    if settings.panel_enabled:
        asyncio.run(_run_with_panel(application, settings))
    else:
        logger.info(
            "Bot is running with polling (admin panel disabled: PANEL_PASSWORD not set)."
        )
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
